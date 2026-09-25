// The Discover list: interest-first rows. What you share is the headline;
// the photo is small. Ranked by shared interests, then distance.

import SwiftUI

struct DiscoverView: View {
    @Environment(AppModel.self) private var model

    @State private var cards: [DiscoverCard] = []
    @State private var loaded = false
    @State private var error: String?
    @State private var justMatched: PublicProfile?

    var body: some View {
        NavigationStack {
            List {
                if let error {
                    Text(error).foregroundStyle(.red)
                }
                ForEach(cards) { card in
                    DiscoverRow(card: card)
                        .swipeActions(edge: .trailing) {
                            Button("Pass") { decide(card, like: false) }.tint(.gray)
                        }
                        .swipeActions(edge: .leading) {
                            Button("Like") { decide(card, like: true) }.tint(.pink)
                        }
                }
            }
            .overlay {
                if loaded && cards.isEmpty && error == nil {
                    // Deliberately no "widen your radius?" offer here.
                    ContentUnavailableView(
                        "Nobody new nearby",
                        systemImage: "person.2",
                        description: Text("Add more interests, or check back later.")
                    )
                }
            }
            .navigationTitle("Discover")
            .toolbar {
                NavigationLink("Passed") { PassedView() }
            }
            .refreshable { await load() }
            .task { await load() }
            .alert(
                "It's a match",
                isPresented: Binding(get: { justMatched != nil }, set: { if !$0 { justMatched = nil } })
            ) {
                Button("Nice") {}
            } message: {
                Text("You and \(justMatched?.firstName ?? "they") liked each other. "
                    + "You can invite each other to parties now.")
            }
        }
    }

    private func load() async {
        do {
            cards = try await model.api.discover()
            error = nil
        } catch {
            self.error = error.localizedDescription
        }
        loaded = true
    }

    private func decide(_ card: DiscoverCard, like: Bool) {
        // Take the row out straight away; put it back if the call fails.
        let index = cards.firstIndex { $0.id == card.id }
        cards.removeAll { $0.id == card.id }
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

struct DiscoverRow: View {
    let card: DiscoverCard

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Avatar(url: card.user.photoUrl, size: 44)
            VStack(alignment: .leading, spacing: 4) {
                if card.suggestedForPartyId != nil {
                    Label("Introduced by a friend", systemImage: "hand.wave")
                        .font(.caption.bold())
                        .foregroundStyle(.orange)
                }
                // The headline: what you have in common.
                Text(card.sharedInterests.joined(separator: " · "))
                    .font(.headline)
                Text(subtitle)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                if let bio = card.user.bio, !bio.isEmpty {
                    Text(bio).font(.footnote).lineLimit(2)
                }
            }
        }
        .padding(.vertical, 4)
    }

    private var subtitle: String {
        var parts = [card.user.firstName ?? "Someone"]
        if let age = card.user.age { parts.append("\(age)") }
        parts.append("\(card.distanceKm) km")
        if card.user.downToParty { parts.append("down to party") }
        return parts.joined(separator: ", ")
    }
}

/// Everyone you passed on. Changed your mind? Like them from here.
struct PassedView: View {
    @Environment(AppModel.self) private var model
    @State private var people: [PassedPerson] = []
    @State private var error: String?

    var body: some View {
        List {
            if let error {
                Text(error).foregroundStyle(.red)
            }
            ForEach(people) { person in
                HStack(spacing: 12) {
                    Avatar(url: person.user.photoUrl, size: 36)
                    VStack(alignment: .leading) {
                        Text(person.user.firstName ?? "Someone").font(.headline)
                        Text(person.sharedInterests.joined(separator: " · "))
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                    }
                    Spacer()
                    Button("Like") { like(person) }
                        .buttonStyle(.bordered)
                        .tint(.pink)
                }
            }
        }
        .overlay {
            if people.isEmpty { ContentUnavailableView("Nobody passed", systemImage: "arrow.uturn.left") }
        }
        .navigationTitle("Passed")
        .task { await load() }
    }

    private func load() async {
        do { people = try await model.api.passed() } catch { self.error = error.localizedDescription }
    }

    private func like(_ person: PassedPerson) {
        Task {
            do {
                _ = try await model.api.like(person.user.id)
                people.removeAll { $0.id == person.id }
            } catch {
                self.error = error.localizedDescription
            }
        }
    }
}

/// A small round photo, or initials-free placeholder when there isn't one.
struct Avatar: View {
    let url: String?
    let size: CGFloat

    var body: some View {
        AsyncImage(url: url.flatMap(URL.init(string:))) { image in
            image.resizable().scaledToFill()
        } placeholder: {
            Image(systemName: "person.fill")
                .foregroundStyle(.secondary)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .background(.quaternary)
        }
        .frame(width: size, height: size)
        .clipShape(Circle())
    }
}
