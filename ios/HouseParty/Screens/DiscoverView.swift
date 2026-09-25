// Discover: interest-first cards. What you share is the headline; the photo
// is small. Ranked by shared interests, then distance.

import SwiftUI

struct DiscoverView: View {
    @Environment(AppModel.self) private var model

    @State private var cards: [DiscoverCard] = []
    @State private var loaded = false
    @State private var error: String?
    @State private var justMatched: PublicProfile?

    var body: some View {
        NavigationStack {
            ScrollView {
                LazyVStack(spacing: 16) {
                    HStack(alignment: .firstTextBaseline) {
                        ScreenTitle(text: "Discover")
                        NavigationLink {
                            PassedView()
                        } label: {
                            Label("Passed", systemImage: "arrow.uturn.backward")
                        }
                        .buttonStyle(.soft(Theme.textDim))
                    }

                    ErrorText(text: error)

                    ForEach(cards) { card in
                        DiscoverCardView(
                            card: card,
                            onLike: { decide(card, like: true) },
                            onPass: { decide(card, like: false) }
                        )
                        .transition(.asymmetric(
                            insertion: .opacity,
                            removal: .scale(scale: 0.9).combined(with: .opacity)
                        ))
                    }

                    if loaded && cards.isEmpty && error == nil {
                        // Deliberately no "widen your radius?" offer here.
                        EmptyState(
                            title: "Nobody new nearby",
                            message: "Add more interests, or check back later.",
                            systemImage: "sparkles"
                        )
                        .padding(.top, 60)
                    }
                }
                .padding(20)
            }
            .partyScreen()
            .toolbarVisibility(.hidden, for: .navigationBar)
            .refreshable { await load() }
            .task { await load() }
            .overlay {
                if let justMatched {
                    MatchCelebration(person: justMatched) { self.justMatched = nil }
                        .transition(.opacity.combined(with: .scale(scale: 1.1)))
                }
            }
            .animation(.smooth, value: justMatched?.id)
        }
    }

    private func load() async {
        do {
            let fresh = try await model.api.discover()
            withAnimation { cards = fresh }
            error = nil
        } catch {
            self.error = error.localizedDescription
        }
        loaded = true
    }

    private func decide(_ card: DiscoverCard, like: Bool) {
        // Take the card out straight away; put it back if the call fails.
        let index = cards.firstIndex { $0.id == card.id }
        withAnimation(.snappy) { cards.removeAll { $0.id == card.id } }
        Task {
            do {
                let result = like ? try await model.api.like(card.user.id)
                                  : try await model.api.pass(card.user.id)
                if result.matched { justMatched = card.user }
            } catch {
                self.error = error.localizedDescription
                if let index { cards.insert(card, at: min(index, cards.count)) }
            }
        }
    }
}

struct DiscoverCardView: View {
    let card: DiscoverCard
    let onLike: () -> Void
    let onPass: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            if card.suggestedForPartyId != nil {
                Badge(text: "Introduced by a friend", systemImage: "hand.wave.fill", color: Theme.orange)
            }

            HStack(spacing: 12) {
                Avatar(url: card.user.photoUrl, name: card.user.firstName, size: 48)
                VStack(alignment: .leading, spacing: 2) {
                    Text(nameAndAge).font(.title3.weight(.bold))
                    Text(placeAndDistance)
                        .font(.subheadline)
                        .foregroundStyle(Theme.textDim)
                }
                Spacer()
                if card.user.downToParty {
                    Badge(text: "down to party", systemImage: "flame.fill", color: Theme.mint)
                }
            }

            // The headline: what you have in common.
            VStack(alignment: .leading, spacing: 8) {
                SectionLabel(card.sharedInterests.count == 1
                             ? "You both love" : "You share \(card.sharedInterests.count)")
                ChipCloud(interests: card.sharedInterests)
            }

            if let bio = card.user.bio, !bio.isEmpty {
                Text(bio)
                    .font(.callout)
                    .foregroundStyle(Theme.text.opacity(0.85))
                    .lineLimit(3)
            }

            HStack(spacing: 12) {
                Button(action: onPass) {
                    Image(systemName: "xmark")
                        .font(.headline.weight(.bold))
                        .frame(width: 22, height: 22)
                }
                .buttonStyle(.soft(Theme.textDim))
                .accessibilityLabel("Pass")

                Button(action: onLike) {
                    Label("Like", systemImage: "heart.fill")
                }
                .buttonStyle(.hot)
            }
        }
        .card(padding: 18)
    }

    private var nameAndAge: String {
        let name = card.user.firstName ?? "Someone"
        return card.user.age.map { "\(name), \($0)" } ?? name
    }

    private var placeAndDistance: String {
        [card.user.neighborhood, "\(card.distanceKm) km away"]
            .compactMap { $0 }
            .joined(separator: " · ")
    }
}

/// Full-screen "It's a match" moment.
struct MatchCelebration: View {
    let person: PublicProfile
    let onClose: () -> Void

    var body: some View {
        ZStack {
            Theme.background.opacity(0.92).ignoresSafeArea()
            VStack(spacing: 20) {
                Avatar(url: person.photoUrl, name: person.firstName, size: 110)
                    .shadow(color: Theme.pink.opacity(0.7), radius: 30)
                Text("It's a match!")
                    .font(.system(size: 44, weight: .black, design: .rounded))
                    .foregroundStyle(Theme.hot)
                Text("You and \(person.firstName ?? "they") liked each other.\n"
                    + "You can invite each other to parties now.")
                    .multilineTextAlignment(.center)
                    .foregroundStyle(Theme.textDim)
                Button("Keep looking", action: onClose)
                    .buttonStyle(.hot)
                    .padding(.top, 8)
            }
            .padding(32)
        }
    }
}

/// Everyone you passed on. Changed your mind? Like them from here.
struct PassedView: View {
    @Environment(AppModel.self) private var model
    @State private var people: [PassedPerson] = []
    @State private var loaded = false
    @State private var error: String?

    var body: some View {
        ScrollView {
            VStack(spacing: 12) {
                ErrorText(text: error)
                ForEach(people) { person in
                    HStack(spacing: 12) {
                        Avatar(url: person.user.photoUrl, name: person.user.firstName, size: 40)
                        VStack(alignment: .leading, spacing: 6) {
                            Text(person.user.firstName ?? "Someone").font(.headline)
                            ChipCloud(interests: person.sharedInterests)
                        }
                        Spacer()
                        Button { like(person) } label: {
                            Image(systemName: "heart.fill")
                        }
                        .buttonStyle(.soft(Theme.pink))
                        .accessibilityLabel("Like \(person.user.firstName ?? "")")
                    }
                    .card(padding: 14)
                }
                if loaded && people.isEmpty {
                    EmptyState(
                        title: "Nobody passed",
                        message: "People you pass on in Discover show up here.",
                        systemImage: "arrow.uturn.backward"
                    )
                }
            }
            .padding(20)
        }
        .partyScreen()
        .navigationTitle("Passed")
        .task { await load() }
    }

    private func load() async {
        do { people = try await model.api.passed() } catch { self.error = error.localizedDescription }
        loaded = true
    }

    private func like(_ person: PassedPerson) {
        Task {
            do {
                _ = try await model.api.like(person.user.id)
                withAnimation { people.removeAll { $0.id == person.id } }
            } catch {
                self.error = error.localizedDescription
            }
        }
    }
}
