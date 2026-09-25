"""Everything House Party runs on in AWS, described as Python.

`cdk deploy` reads this and creates (or updates) exactly this, so this file
is the whole truth about the production setup. In plain terms:

  phone ──HTTPS──> CloudFront ──> load balancer ──> the server (ECS Fargate)
                        │                               │         │
                        └── /photos/* ──> S3 bucket <───┘         └──> Postgres (RDS)

  * CloudFront gives us a free https://....cloudfront.net address until we
    buy a domain, and serves photos from S3 close to the phone.
  * The load balancer only answers requests that come through CloudFront
    (they carry a secret header), so nobody can skip past it.
  * The database has no internet access at all; only the server can reach it.
  * Secrets (database password, login signing key, admin password, Twilio)
    live in Secrets Manager and are handed to the server when it starts.

Costs roughly $60-80/month at rest: the database and load balancer are most
of it. There is deliberately no NAT gateway (another ~$35/month): the server
sits in a public subnet with its own address and a firewall instead.
"""

from aws_cdk import (
    CfnOutput,
    Duration,
    RemovalPolicy,
    SecretValue,
    Stack,
)
from aws_cdk import aws_cloudfront as cloudfront
from aws_cdk import aws_cloudfront_origins as origins
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_ecr_assets as ecr_assets
from aws_cdk import aws_ecs as ecs
from aws_cdk import aws_ecs_patterns as ecs_patterns
from aws_cdk import aws_elasticloadbalancingv2 as elbv2
from aws_cdk import aws_iam as iam
from aws_cdk import aws_logs as logs
from aws_cdk import aws_rds as rds
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_secretsmanager as secretsmanager
from constructs import Construct

ORIGIN_HEADER = "X-Origin-Verify"


class HousePartyStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # --- Network -------------------------------------------------------
        # Two availability zones (AWS requires two for the database and load
        # balancer). "Public" subnets reach the internet; "Database" subnets
        # can't, in either direction.
        vpc = ec2.Vpc(
            self,
            "Network",
            max_azs=2,
            nat_gateways=0,
            subnet_configuration=[
                ec2.SubnetConfiguration(name="Public", subnet_type=ec2.SubnetType.PUBLIC),
                ec2.SubnetConfiguration(
                    name="Database", subnet_type=ec2.SubnetType.PRIVATE_ISOLATED
                ),
            ],
        )

        # --- Database ------------------------------------------------------
        database = rds.DatabaseInstance(
            self,
            "Database",
            engine=rds.DatabaseInstanceEngine.postgres(
                version=rds.PostgresEngineVersion.VER_16
            ),
            instance_type=ec2.InstanceType.of(ec2.InstanceClass.T4G, ec2.InstanceSize.MICRO),
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_ISOLATED),
            database_name="houseparty",
            # A random password, stored in Secrets Manager. Nobody types it.
            credentials=rds.Credentials.from_generated_secret("houseparty"),
            storage_encrypted=True,
            allocated_storage=20,
            max_allocated_storage=100,
            backup_retention=Duration.days(7),
            # Deleting the stack keeps a final snapshot rather than the data
            # just vanishing. Switch on deletion_protection once it's real.
            removal_policy=RemovalPolicy.SNAPSHOT,
            deletion_protection=False,
        )

        # --- Photos --------------------------------------------------------
        photos = s3.Bucket(
            self,
            "Photos",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,  # only CloudFront reads it
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            removal_policy=RemovalPolicy.RETAIN,
        )

        # --- Secrets -------------------------------------------------------
        def random_secret(name: str, description: str) -> secretsmanager.Secret:
            return secretsmanager.Secret(
                self,
                name,
                description=description,
                generate_secret_string=secretsmanager.SecretStringGenerator(
                    password_length=48, exclude_punctuation=True
                ),
            )

        jwt_secret = random_secret("JwtSecret", "Signs House Party login tokens")
        admin_session = random_secret("AdminSessionSecret", "Signs admin page sessions")
        admin_password = random_secret("AdminPassword", "Password for the /admin page")
        origin_secret = random_secret("OriginSecret", "Proves a request came through CloudFront")

        # Twilio keys: created empty, filled in by hand (see DEPLOY.md).
        twilio = secretsmanager.Secret(
            self,
            "Twilio",
            description="Twilio Verify keys for sign-in texts",
            secret_object_value={
                "account_sid": SecretValue.unsafe_plain_text(""),
                "auth_token": SecretValue.unsafe_plain_text(""),
                "verify_service_sid": SecretValue.unsafe_plain_text(""),
            },
        )

        # --- The server ----------------------------------------------------
        cluster = ecs.Cluster(self, "Cluster", vpc=vpc)
        service = ecs_patterns.ApplicationLoadBalancedFargateService(
            self,
            "Api",
            cluster=cluster,
            cpu=512,  # half a CPU
            memory_limit_mib=1024,
            # One copy on purpose: live chat and the party reminder job
            # assume a single server for now.
            desired_count=1,
            # During an update, start the new copy before stopping the old one,
            # so the app never goes down for a deploy.
            min_healthy_percent=100,
            public_load_balancer=True,
            assign_public_ip=True,
            task_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            runtime_platform=ecs.RuntimePlatform(
                cpu_architecture=ecs.CpuArchitecture.ARM64,
                operating_system_family=ecs.OperatingSystemFamily.LINUX,
            ),
            circuit_breaker=ecs.DeploymentCircuitBreaker(rollback=True),
            # Room for the database update that runs at startup.
            health_check_grace_period=Duration.seconds(120),
            task_image_options=ecs_patterns.ApplicationLoadBalancedTaskImageOptions(
                image=ecs.ContainerImage.from_asset(
                    "../backend", platform=ecr_assets.Platform.LINUX_ARM64
                ),
                container_port=8000,
                log_driver=ecs.LogDrivers.aws_logs(
                    stream_prefix="api",
                    log_group=logs.LogGroup(
                        self,
                        "ApiLogs",
                        retention=logs.RetentionDays.ONE_MONTH,
                        removal_policy=RemovalPolicy.DESTROY,
                    ),
                ),
                environment={
                    "ENV": "production",
                    "DB_HOST": database.db_instance_endpoint_address,
                    "DB_PORT": database.db_instance_endpoint_port,
                    "DB_NAME": "houseparty",
                    "STORAGE_BACKEND": "s3",
                    "S3_BUCKET": photos.bucket_name,
                    "MODERATION_BACKEND": "rekognition",
                    "AWS_REGION": self.region,
                    # Testing only: until Twilio is filled in, sign-in codes go
                    # to the server log. Remove this line before real users.
                    "ALLOW_LOGGED_CODES": "true",
                },
                secrets={
                    "DB_USERNAME": ecs.Secret.from_secrets_manager(database.secret, "username"),
                    "DB_PASSWORD": ecs.Secret.from_secrets_manager(database.secret, "password"),
                    "JWT_SECRET": ecs.Secret.from_secrets_manager(jwt_secret),
                    "ADMIN_SESSION_SECRET": ecs.Secret.from_secrets_manager(admin_session),
                    "ADMIN_PASSWORD": ecs.Secret.from_secrets_manager(admin_password),
                    "TWILIO_ACCOUNT_SID": ecs.Secret.from_secrets_manager(twilio, "account_sid"),
                    "TWILIO_AUTH_TOKEN": ecs.Secret.from_secrets_manager(twilio, "auth_token"),
                    "TWILIO_VERIFY_SERVICE_SID": ecs.Secret.from_secrets_manager(
                        twilio, "verify_service_sid"
                    ),
                },
            ),
        )
        service.target_group.configure_health_check(path="/healthz")
        # Chat connections stay open; don't cut them after the default minute.
        service.load_balancer.set_attribute("idle_timeout.timeout_seconds", "3600")

        # Only the server can reach the database.
        database.connections.allow_default_port_from(service.service)
        # The server may save photos and ask Rekognition about them.
        photos.grant_put(service.task_definition.task_role)
        service.task_definition.task_role.add_to_principal_policy(
            iam.PolicyStatement(actions=["rekognition:DetectModerationLabels"], resources=["*"])
        )

        # The load balancer turns away anything that didn't come through
        # CloudFront: requests must carry the secret header.
        listener_resource = service.listener.node.default_child
        listener_resource.default_actions = [  # type: ignore[attr-defined]
            {
                "type": "fixed-response",
                "fixedResponseConfig": {"statusCode": "403", "contentType": "text/plain"},
            }
        ]
        service.listener.add_action(
            "FromCloudFront",
            priority=1,
            conditions=[
                elbv2.ListenerCondition.http_header(
                    ORIGIN_HEADER, [origin_secret.secret_value.unsafe_unwrap()]
                )
            ],
            action=elbv2.ListenerAction.forward([service.target_group]),
        )

        # --- CloudFront: the one public address ----------------------------
        distribution = cloudfront.Distribution(
            self,
            "Cdn",
            comment="House Party API and photos",
            price_class=cloudfront.PriceClass.PRICE_CLASS_100,  # US, Canada, Europe
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.LoadBalancerV2Origin(
                    service.load_balancer,
                    protocol_policy=cloudfront.OriginProtocolPolicy.HTTP_ONLY,
                    custom_headers={ORIGIN_HEADER: origin_secret.secret_value.unsafe_unwrap()},
                    read_timeout=Duration.seconds(60),
                ),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                allowed_methods=cloudfront.AllowedMethods.ALLOW_ALL,
                # The API is never cached: every answer is personal.
                cache_policy=cloudfront.CachePolicy.CACHING_DISABLED,
                origin_request_policy=cloudfront.OriginRequestPolicy.ALL_VIEWER_EXCEPT_HOST_HEADER,
            ),
            additional_behaviors={
                "/photos/*": cloudfront.BehaviorOptions(
                    origin=origins.S3BucketOrigin.with_origin_access_control(photos),
                    viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                    cache_policy=cloudfront.CachePolicy.CACHING_OPTIMIZED,
                ),
            },
        )

        # --- What you need after deploying ---------------------------------
        CfnOutput(
            self,
            "ApiUrl",
            value=f"https://{distribution.distribution_domain_name}",
            description="Put this in API_BASE_URL (Release) in Xcode",
        )
        CfnOutput(self, "AdminPasswordSecretName", value=admin_password.secret_name)
        CfnOutput(self, "TwilioSecretName", value=twilio.secret_name)
        CfnOutput(self, "LogGroup", value=service.task_definition.default_container.log_driver_config.options["awslogs-group"])  # type: ignore[union-attr]
