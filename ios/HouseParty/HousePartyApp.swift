import SwiftUI

@main
struct HousePartyApp: App {
    @UIApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate
    @State private var model = AppModel()

    init() {
        // Navigation bar titles are drawn by UIKit, which ignores SwiftUI's
        // font settings, so give them the app's typeface here.
        let bar = UINavigationBar.appearance()
        bar.titleTextAttributes = [
            .font: Theme.uiFont(size: 17, weight: .semibold),
            .foregroundColor: UIColor(Theme.text),
        ]
        bar.largeTitleTextAttributes = [
            .font: Theme.uiFont(size: 34, weight: .bold),
            .foregroundColor: UIColor(Theme.text),
        ]
    }

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(model)
                .task {
                    AppDelegate.onToken = { model.registerPush(token: $0) }
                    AppDelegate.onRoute = { model.route = $0 }
                    await model.start()
                }
                .onOpenURL { url in
                    if let route = Route(url: url) { model.route = route }
                }
                // Always dark: it's a nightlife app.
                .preferredColorScheme(.dark)
                .tint(Theme.pink)
                .fontDesign(Theme.fontDesign)
        }
    }
}

/// Picks the screen for where you are: signing in, setting up, or in.
struct RootView: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        switch model.phase {
        case .loading:
            ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity).partyScreen()
        case .signedOut:
            SignInView()
        case .onboarding:
            OnboardingView()
        case .ready:
            MainTabs()
        }
    }
}

struct MainTabs: View {
    @Environment(AppModel.self) private var model

    enum Section: Hashable { case match, parties, chats, me }
    @State private var section: Section = .match

    var body: some View {
        TabView(selection: $section) {
            Tab(value: Section.match) {
                DiscoverView()
            } label: {
                Label {
                    Text("Match")
                } icon: {
                    Image(uiImage: EmojiIcon.image("🤝"))
                }
            }
            Tab(value: Section.parties) {
                PartiesView()
            } label: {
                Label { Text("Parties") } icon: { Image(uiImage: TabIcon.soloCup) }
            }
            Tab(value: Section.chats) {
                ChatsView()
            } label: {
                Label { Text("Chats") } icon: { Image(uiImage: TabIcon.chats) }
            }
            Tab("Me", image: "AcidSmiley", value: Section.me) {
                ProfileView()
            }
        }
        // Once you're in, ask about notifications (only prompts the first time).
        .task { await Notifications.enable() }
        // A tapped notification: jump to the right tab; that tab opens the
        // exact chat, party or person.
        .onChange(of: model.route) { _, route in
            switch route {
            case .chat: section = .chats
            case .party: section = .parties
            case .person: section = .match
            case nil: break
            }
        }
    }
}

/// Placeholder for tabs that aren't built yet.
struct ComingSoon: View {
    let title: String

    var body: some View {
        VStack(alignment: .leading) {
            ScreenTitle(text: title)
            Spacer()
            EmptyState(title: "Coming next", message: "This part is being built.", systemImage: "hammer.fill")
            Spacer()
        }
        .padding(20)
        .partyScreen()
    }
}
