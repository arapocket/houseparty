# Putting House Party on AWS

Everything AWS runs is described in `infra/stack.py` (read the top of it for
the picture). These steps create it in your account. Nothing is created or
billed until step 4.

**Cost:** roughly $60–80/month while it's running, mostly the database and the
load balancer. `cdk destroy` (at the bottom) stops the charges.

## One-time setup on this Mac

### 1. Install the tools

```bash
brew install awscli colima docker
```

- `awscli` lets this Mac talk to your AWS account.
- `colima` + `docker` build the server into a package AWS can run. (Colima is
  a free, command-line alternative to Docker Desktop.)

Start Colima once per restart of the Mac, before deploying:

```bash
colima start --arch aarch64
```

### 2. Sign this Mac in to AWS

Don't use your AWS root login for this. In the AWS console:

1. Open **IAM Identity Center** and enable it (it's free).
2. Create a user for yourself and give it the **AdministratorAccess**
   permission set on your account.
3. Note the **AWS access portal URL** it shows you.

Then, on the Mac:

```bash
aws configure sso
```

Answer with the portal URL, region `us-east-1`, and name the profile
`houseparty`. From then on, in each new terminal:

```bash
export AWS_PROFILE=houseparty
aws sso login
```

Check it worked (it prints your account number):

```bash
aws sts get-caller-identity
```

### 3. Prepare the account for CDK (once per account)

```bash
cd ~/houseparty/infra
npx aws-cdk@2 bootstrap
```

## Deploying

### 4. Deploy

```bash
cd ~/houseparty/infra
npx aws-cdk@2 deploy
```

It shows what it's about to create and asks you to confirm. The first deploy
takes 15–25 minutes (the database and CloudFront are slow to create). Later
deploys, after code changes, take a few minutes.

At the end it prints:

- **ApiUrl**: `https://something.cloudfront.net`. That's the server.
- **AdminPasswordSecretName**, **TwilioSecretName**, **LogGroup**.

Check it's alive:

```bash
curl https://YOUR-API-URL/healthz
```

### 5. Point the app at it

In Xcode: the project → the HouseParty target → Build Settings → search
`API_BASE_URL` → set **Release** to the ApiUrl. (Debug stays on your Mac.)

### 6. The admin page password

```bash
aws secretsmanager get-secret-value --secret-id ADMIN-PASSWORD-SECRET-NAME --query SecretString --output text
```

Log in at `https://YOUR-API-URL/admin` with username `admin`.

### 7. Sign-in texts

Until Twilio is set up, sign-in codes are written to the server log (this is
switched on by `ALLOW_LOGGED_CODES` in `stack.py`, for testing only). To read
the latest ones:

```bash
aws logs tail LOG-GROUP-NAME --since 10m | grep "verification code"
```

To turn on real texts, fill in the Twilio secret, then restart the server:

```bash
aws secretsmanager put-secret-value --secret-id TWILIO-SECRET-NAME \
  --secret-string '{"account_sid":"AC...","auth_token":"...","verify_service_sid":"VA..."}'
aws ecs update-service --cluster CLUSTER --service SERVICE --force-new-deployment
```

(Cluster and service names are in the ECS console, or ask Claude.) Then
delete the `ALLOW_LOGGED_CODES` line in `stack.py` and deploy again.

## Before real users

- Buy a domain (Route 53 is easiest) and put it in front of CloudFront with an
  HTTPS certificate. Also switch CloudFront → load balancer to HTTPS.
- Remove `ALLOW_LOGGED_CODES` (see step 7).
- In `stack.py`, set `deletion_protection=True` on the database.
- Push notifications: add the Apple keys as another secret (see HANDOFF.md).

## Tearing it down

```bash
cd ~/houseparty/infra
npx aws-cdk@2 destroy
```

The database leaves a final snapshot and the photo bucket is kept, so nothing
is lost by accident. Delete those by hand in the console if you really mean it.
