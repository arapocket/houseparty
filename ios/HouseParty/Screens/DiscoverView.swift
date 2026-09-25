// Discover: interest-first cards. What you share is the headline; the photo
// is small. Ranked by shared interests, then distance.

import SwiftUI

struct DiscoverView: View {
    @Environment(AppModel.self) private var model

    @State private var cards: [DiscoverCard] = []
    @State private var loaded = false
    @State private var error: String?
    @State private var justMatched: PublicProfile?
    @State private var viewing: PersonRef?

    var body: some View {
        NavigationStack {
            ScrollView {
                LazyVStack(spacing: 16) {
                    HStack(alignment: .firstTextBaseline) {
                        ScreenTitle(text: "Match")
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
                        .contentShape(.rect)
                        .onTapGesture { viewing = PersonRef(id: card.user.id) }
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
            .task(id: model.route) {
                guard case .person(let id) = model.route else { return }
                model.route = nil
                viewing = PersonRef(id: id)
            }
            .personSheet($viewing, showDecision: true) { _ in
                // They're decided on now, so they leave the list.
                if let id = viewing?.id {
                    withAnimation { cards.removeAll { $0.user.id == id } }
                }
            }
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
                Badge(text: "Introduced by a friend", systemImage: "hand.wave.fill", color: Theme.blue)
            }

            HStack(spacing: 12) {
                Avatar(url: card.user.photoUrl, name: card.user.firstName, size: 48)
                VStack(alignment: .leading, spacing: 2) {
                    Text(nameAndAge).font(.title3.weight(.bold))
                    Text(placeAndDistance)
                        .font(.subheadline)
                        .foregroundStyle(Theme.textDim)
                    if card.user.downToParty {
                        Badge(text: "down to party", systemImage: "flame.fill", color: Theme.mint)
                            .padding(.top, 4)
                    }
                }
                Spacer()
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
                    HStack(spacing: 8) {
                        AcidSmiley(size: 24)
                        Text("Like")
                    }
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
                ZStack(alignment: .bottomTrailing) {
                    Avatar(url: person.photoUrl, name: person.firstName, size: 110)
                        .shadow(color: Theme.pink.opacity(0.7), radius: 30)
                    AcidSmiley(size: 54, spinning: true)
                        .shadow(color: AcidSmiley.yellow.opacity(0.6), radius: 14)
                        .offset(x: 14, y: 8)
                }
                Text("It's a match!")
                    .font(.system(size: 44, weight: .black, design: Theme.fontDesign))
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
    @State private var viewing: PersonRef?

    var body: some View {
        ScrollView {
            VStack(spacing: 12) {
                ErrorText(text: error)
                ForEach(people) { person in
                    HStack(spacing: 12) {
                        Avatar(url: person.user.photoUrl, name: person.user.firstName, size: 40)
                        VStack(alignment: .leading, spacing: 6) {
                            Text(person.user.firstName ?? "Someone").font(.headline)
                            Text([person.user.age.map(String.init), person.user.neighborhood]
                                .compactMap { $0 }.joined(separator: " · "))
                                .font(.subheadline)
                                .foregroundStyle(Theme.textDim)
                            if !person.sharedInterests.isEmpty {
                                ChipCloud(interests: person.sharedInterests)
                            }
                        }
                        Spacer()
                        Button { like(person) } label: {
                            AcidSmiley(size: 22)
                        }
                        .buttonStyle(.soft(Theme.pink))
                        .accessibilityLabel("Like \(person.user.firstName ?? "")")
                    }
                    .card(padding: 14)
                    // Tapping anywhere but the smiley opens their profile.
                    .contentShape(.rect)
                    .onTapGesture { viewing = PersonRef(id: person.user.id) }
                }
                if loaded && people.isEmpty {
                    EmptyState(
                        title: "Nobody passed",
                        message: "People you pass on in Match show up here.",
                        systemImage: "arrow.uturn.backward"
                    )
                }
            }
            .padding(20)
        }
        .partyScreen()
        .navigationTitle("Passed")
        .task { await load() }
        .personSheet($viewing, showDecision: true) { _ in
            Task { await load() }
        }
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
