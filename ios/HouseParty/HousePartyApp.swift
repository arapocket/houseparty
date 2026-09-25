import SwiftUI

@main
struct HousePartyApp: App {
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
                .task { await model.start() }
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
    var body: some View {
        TabView {
            Tab {
                DiscoverView()
            } label: {
                Label {
                    Text("Match")
                } icon: {
                    Image(uiImage: EmojiIcon.image("🤝"))
                }
            }
            Tab("Parties", image: "SoloCup") {
                PartiesView()
            }
            Tab("Chats", systemImage: "bubble.left.and.bubble.right.fill") {
                ChatsView()
            }
            Tab("Me", image: "AcidSmiley") {
                ProfileView()
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
