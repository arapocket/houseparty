// Someone's full profile: big photo, who they are, all their interests
// (the ones you share lit up), and what you can do about them.
//
// Opens as a sheet from anywhere a person shows up: Match, Passed, chat
// members, guest lists.

import SwiftUI

struct PersonView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss

    let userId: UUID
    /// Show Like / Pass buttons. Off where it makes no sense (e.g. a chat).
    var showDecision = false
    /// Called after you like, pass or block, so the list behind can update.
    var onDecided: (Bool) -> Void = { _ in }

    @State private var person: PublicProfile?
    @State private var confirmingBlock = false
    @State private var justMatched = false
    @State private var error: String?
    @State private var notice: String?

    private var myInterests: Set<String> { Set(model.me?.interests ?? []) }

    var body: some View {
        NavigationStack {
            ScrollView {
                if let person {
                    VStack(alignment: .leading, spacing: 20) {
                        header(person)
                        if let bio = person.bio, !bio.isEmpty {
                            Text(bio).font(.body)
                        }
                        VStack(alignment: .leading, spacing: 10) {
                            SectionLabel("Into")
                            ChipCloud(interests: person.interests, sharedWithMe: myInterests)
                            Text("Filled in: you're both into it.")
                                .font(.caption)
                                .foregroundStyle(Theme.textDim)
                        }
                        .card()

                        ErrorText(text: error)
                        if let notice {
                            Text(notice).font(.subheadline.weight(.semibold)).foregroundStyle(Theme.mint)
                        }

                        if showDecision {
                            HStack(spacing: 12) {
                                Button { decide(like: false) } label: {
                                    Image(systemName: "xmark").font(.headline.weight(.bold)).frame(width: 22, height: 22)
                                }
                                .buttonStyle(.soft(Theme.textDim))
                                .accessibilityLabel("Pass")
                                Button { decide(like: true) } label: {
                                    HStack(spacing: 8) { AcidSmiley(size: 24); Text("Like") }
                                }
                                .buttonStyle(.hot)
                            }
                        }

                        safetyButtons(person)
                    }
                    .padding(20)
                } else if error == nil {
                    ProgressView().padding(.top, 120)
                } else {
                    ErrorText(text: error).padding(20)
                }
            }
            .partyScreen()
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } }
            }
            .overlay {
                if justMatched, let person {
                    MatchCelebration(person: person) { dismiss() }
                }
            }
            .confirmationDialog(
                "Block \(person?.firstName ?? "them")?",
                isPresented: $confirmingBlock,
                titleVisibility: .visible
            ) {
                Button("Block", role: .destructive, action: block)
            } message: {
                Text("You won't see each other anywhere in House Party again. They aren't told.")
            }
            .task { await load() }
        }
    }

    private func header(_ person: PublicProfile) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            AsyncImage(url: APIClient.mediaURL(person.photoUrl)) { image in
                image.resizable().scaledToFill()
            } placeholder: {
                Text(person.firstName?.first.map(String.init) ?? "?")
                    .font(.system(size: 96, weight: .heavy, design: Theme.fontDesign))
                    .foregroundStyle(.white)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .background(
                        LinearGradient(
                            colors: [Theme.color(for: person.firstName ?? "?"), Theme.violet],
                            startPoint: .topLeading, endPoint: .bottomTrailing
                        )
                    )
            }
            .frame(height: 340)
            .frame(maxWidth: .infinity)
            .clipShape(.rect(cornerRadius: Theme.corner))

            VStack(alignment: .leading, spacing: 6) {
                Text([person.firstName, person.age.map(String.init)].compactMap { $0 }.joined(separator: ", "))
                    .font(.system(size: 32, weight: .heavy, design: Theme.fontDesign))
                if let hood = person.neighborhood {
                    Label(hood, systemImage: "mappin.and.ellipse").foregroundStyle(Theme.textDim)
                }
                if person.downToParty {
                    Badge(text: "down to party", systemImage: "flame.fill", color: Theme.mint)
                }
            }
        }
    }

    private func safetyButtons(_ person: PublicProfile) -> some View {
        HStack(spacing: 12) {
            Button("Report") {
                run("Reported. Thanks for telling us.") {
                    try await model.api.report(NewReport(subjectUserId: person.id, reason: "profile"))
                }
            }
            .buttonStyle(.soft(Theme.textDim))
            Button("Block") { confirmingBlock = true }
                .buttonStyle(.soft(Theme.pink))
        }
        .frame(maxWidth: .infinity)
        .padding(.top, 8)
    }

    // MARK: Actions

    private func load() async {
        do { person = try await model.api.profile(userId) } catch {
            self.error = error.localizedDescription
        }
    }

    private func decide(like: Bool) {
        Task {
            do {
                let result = like ? try await model.api.like(userId) : try await model.api.pass(userId)
                onDecided(like)
                if result.matched {
                    withAnimation { justMatched = true }
                } else {
                    dismiss()
                }
            } catch {
                self.error = error.localizedDescription
            }
        }
    }

    private func block() {
        Task {
            do {
                try await model.api.block(userId)
                onDecided(false)
                dismiss()
            } catch {
                self.error = error.localizedDescription
            }
        }
    }

    private func run(_ done: String, _ work: @escaping () async throws -> Void) {
        Task {
            do {
                try await work()
                notice = done
                error = nil
            } catch {
                self.error = error.localizedDescription
            }
        }
    }
}

/// Lets any list open a person with `.personSheet($selected)`.
struct PersonRef: Identifiable, Hashable {
    let id: UUID
}

extension View {
    func personSheet(
        _ selection: Binding<PersonRef?>,
        showDecision: Bool = false,
        onDecided: @escaping (Bool) -> Void = { _ in }
    ) -> some View {
        sheet(item: selection) { ref in
            PersonView(userId: ref.id, showDecision: showDecision, onDecided: onDecided)
        }
    }
}
