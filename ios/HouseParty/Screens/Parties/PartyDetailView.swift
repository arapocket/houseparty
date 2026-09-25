// One party. What you can do depends on who you are:
//
//   host      invite matches, see the guest list, remove people, ask for a
//             bigger party, cancel
//   invited   see the host, who's going, roughly where; accept or decline
//   going     see the address; suggest someone; back out

import SwiftUI

struct PartyDetailView: View {
    @Environment(AppModel.self) private var model

    let partyId: UUID
    let inviteId: UUID?
    /// Tells the party list to reload after something changed.
    var onChange: () -> Void = {}

    @State private var party: Party?
    @State private var guests: [Guest] = []
    @State private var picking: PickerMode?
    @State private var confirmingCancel = false
    @State private var askingBigger = false
    @State private var error: String?

    enum PickerMode: Identifiable {
        case invite, suggest
        var id: Self { self }
    }

    private var role: String { party?.myInviteStatus ?? "" }
    private var isActive: Bool { party?.status == "active" }

    var body: some View {
        ScrollView {
            if let party {
                VStack(alignment: .leading, spacing: 18) {
                    header(party)
                    details(party)
                    ErrorText(text: error)
                    actions(party)
                    if role == "host" {
                        guestList
                    } else if !party.guests.isEmpty {
                        whosGoing(party)
                    }
                }
                .padding(20)
            } else {
                ProgressView().padding(.top, 80)
            }
        }
        .partyScreen()
        .navigationBarTitleDisplayMode(.inline)
        .task { await load() }
        .sheet(item: $picking) { mode in
            MatchPicker(
                title: mode == .invite ? "Invite" : "Suggest someone",
                actionLabel: mode == .invite ? "Invite" : "Suggest",
                hint: mode == .invite
                    ? "You can invite anyone you've matched with."
                    : "The host can only invite their matches, so we'll introduce you: "
                      + "they'll show up at the top of each other's Match tab.",
                excluded: Set(guests.map(\.user.id) + (party.map { [$0.host.id] } ?? []))
            ) { person in
                if mode == .invite {
                    _ = try await model.api.invite(person.id, to: partyId)
                } else {
                    try await model.api.suggest(person.id, for: partyId)
                }
                await load()
            }
        }
        .confirmationDialog("Cancel this party?", isPresented: $confirmingCancel, titleVisibility: .visible) {
            Button("Cancel the party", role: .destructive) { run { _ = try await model.api.cancelParty(partyId) } }
        } message: {
            Text("Everyone invited will see it's off. The chat stays open so you can sort out what's next.")
        }
        .alert("Ask for a bigger party", isPresented: $askingBigger) {
            Button("Ask for 40") { run { try await model.api.askForBiggerParty(partyId, cap: 40, reason: nil) } }
            Button("Not now", role: .cancel) {}
        } message: {
            Text("Parties are capped at \(party?.guestCap ?? 20) invites. Someone from House Party reviews bigger ones.")
        }
    }

    // MARK: Pieces

    private func header(_ party: Party) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            if party.status != "active" {
                Badge(
                    text: party.status == "cancelled" ? "Cancelled" : "Happened",
                    systemImage: party.status == "cancelled" ? "xmark.circle.fill" : "checkmark.circle.fill",
                    color: party.status == "cancelled" ? Theme.pink : Theme.violet
                )
            }
            Text(party.title)
                .font(.system(size: 34, weight: .heavy, design: Theme.fontDesign))
                .foregroundStyle(Theme.hot)
            ChipCloud(interests: party.interests)
            HStack(spacing: 10) {
                Avatar(url: party.host.photoUrl, name: party.host.firstName, size: 32)
                Text(role == "host" ? "You're hosting" : "Hosted by \(party.host.firstName ?? "someone")")
                    .font(.subheadline.weight(.semibold))
            }
            .padding(.top, 4)
        }
    }

    private func details(_ party: Party) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            InfoLine(icon: "calendar", color: Theme.blue, text: whenText(party))
            InfoLine(
                icon: "mappin.and.ellipse", color: Theme.cyan,
                text: [party.neighborhood, party.distanceKm.map { "\($0) km away" }]
                    .compactMap { $0 }.joined(separator: " · ")
            )
            if let address = party.address {
                InfoLine(icon: "house.fill", color: Theme.mint, text: address)
            } else if role != "host" {
                InfoLine(icon: "lock.fill", color: Theme.textDim, text: "Exact address shows once you're in")
            }
            InfoLine(
                icon: "person.2.fill", color: Theme.violet,
                text: "\(party.guestCount) going" + (role == "host" ? " · \(party.invitesLeft) invites left" : "")
            )
            if let description = party.description, !description.isEmpty {
                Text(description).foregroundStyle(Theme.text.opacity(0.9))
            }
        }
        .card()
    }

    @ViewBuilder
    private func actions(_ party: Party) -> some View {
        if isActive {
            switch role {
            case "pending":
                HStack(spacing: 12) {
                    Button("Can't make it") { answer(false) }.buttonStyle(.soft(Theme.textDim))
                    Button("I'm in") { answer(true) }.buttonStyle(.hot)
                }
            case "accepted":
                VStack(spacing: 12) {
                    Button { picking = .suggest } label: {
                        Label("Suggest someone", systemImage: "person.badge.plus")
                    }
                    .buttonStyle(.hot)
                    Button("I can't make it anymore") { answer(false) }
                        .buttonStyle(.soft(Theme.textDim))
                }
            case "host":
                VStack(spacing: 12) {
                    Button { picking = .invite } label: {
                        Label("Invite matches", systemImage: "paperplane.fill")
                    }
                    .buttonStyle(.hot)
                    .disabled(party.invitesLeft == 0)
                    HStack(spacing: 12) {
                        Button("Bigger party?") { askingBigger = true }.buttonStyle(.soft(Theme.violet))
                        Button("Cancel party") { confirmingCancel = true }.buttonStyle(.soft(Theme.pink))
                    }
                }
            default:
                EmptyView()
            }
        }
    }

    private var guestList: some View {
        VStack(alignment: .leading, spacing: 12) {
            SectionLabel("Guest list")
            if guests.isEmpty {
                Text("Nobody invited yet.").foregroundStyle(Theme.textDim)
            }
            ForEach(guests) { guest in
                HStack(spacing: 12) {
                    Avatar(url: guest.user.photoUrl, name: guest.user.firstName, size: 36)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(guest.user.firstName ?? "Someone").font(.headline)
                        Text(guestStatus(guest.status))
                            .font(.caption.weight(.bold))
                            .foregroundStyle(guestColor(guest.status))
                    }
                    Spacer()
                    if isActive {
                        Button {
                            run { try await model.api.removeGuest(inviteId: guest.inviteId, from: partyId) }
                        } label: {
                            Image(systemName: "person.fill.xmark")
                        }
                        .buttonStyle(.soft(Theme.textDim))
                        .accessibilityLabel("Remove \(guest.user.firstName ?? "guest")")
                    }
                }
            }
        }
        .card()
    }

    private func whosGoing(_ party: Party) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            SectionLabel("Who's going")
            FlowLayout(spacing: 12) {
                ForEach(party.guests) { guest in
                    VStack(spacing: 4) {
                        Avatar(url: guest.photoUrl, name: guest.firstName, size: 44)
                        Text(guest.firstName ?? "").font(.caption.weight(.semibold))
                    }
                }
            }
        }
        .card()
    }

    // MARK: Actions

    private func load() async {
        do {
            let fresh = try await model.api.party(partyId)
            party = fresh
            if fresh.myInviteStatus == "host" {
                guests = try await model.api.guests(of: partyId)
            }
            error = nil
        } catch {
            self.error = error.localizedDescription
        }
    }

    private func answer(_ accept: Bool) {
        guard let inviteId else { return }
        run { _ = try await model.api.answer(inviteId, accept: accept) }
    }

    /// Do something, then refresh this page and the list behind it.
    private func run(_ work: @escaping () async throws -> Void) {
        Task {
            do {
                try await work()
                await load()
                onChange()
            } catch {
                self.error = error.localizedDescription
            }
        }
    }

    // MARK: Text

    private func whenText(_ party: Party) -> String {
        let start = party.startsAt.formatted(.dateTime.weekday(.wide).month().day().hour().minute())
        guard let end = party.endsAt else { return start }
        return "\(start) – \(end.formatted(date: .omitted, time: .shortened))"
    }

    private func guestStatus(_ status: String) -> String {
        switch status {
        case "accepted": "Going"
        case "pending": "Invited"
        case "declined": "Can't make it"
        default: status.capitalized
        }
    }

    private func guestColor(_ status: String) -> Color {
        switch status {
        case "accepted": Theme.mint
        case "pending": Theme.blue
        default: Theme.textDim
        }
    }
}

struct InfoLine: View {
    let icon: String
    let color: Color
    let text: String

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: icon)
                .font(.subheadline.weight(.bold))
                .foregroundStyle(color)
                .frame(width: 32, height: 32)
                .background(color.opacity(0.15), in: .rect(cornerRadius: 6))
            Text(text).font(.subheadline.weight(.medium))
        }
    }
}

/// Pick one of your matches, to invite or to suggest.
struct MatchPicker: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss

    let title: String
    let actionLabel: String
    let hint: String
    let excluded: Set<UUID>
    let onPick: (PublicProfile) async throws -> Void

    @State private var matches: [MatchRow] = []
    @State private var done: Set<UUID> = []
    @State private var loaded = false
    @State private var error: String?

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    Text(hint).font(.footnote).foregroundStyle(Theme.textDim)
                    ErrorText(text: error)
                    ForEach(matches.filter { !excluded.contains($0.user.id) }) { match in
                        HStack(spacing: 12) {
                            Avatar(url: match.user.photoUrl, name: match.user.firstName, size: 40)
                            VStack(alignment: .leading, spacing: 4) {
                                HStack(spacing: 6) {
                                    Text(match.user.firstName ?? "Someone").font(.headline)
                                    if match.user.downToParty {
                                        Image(systemName: "flame.fill").foregroundStyle(Theme.mint)
                                    }
                                }
                                ChipCloud(interests: Array(match.sharedInterests.prefix(3)))
                            }
                            Spacer()
                            if done.contains(match.user.id) {
                                Image(systemName: "checkmark.circle.fill")
                                    .font(.title2)
                                    .foregroundStyle(Theme.mint)
                            } else {
                                Button(actionLabel) { pick(match.user) }
                                    .buttonStyle(.soft(Theme.pink))
                            }
                        }
                        .card(padding: 14)
                    }
                    if loaded && matches.isEmpty {
                        EmptyState(
                            title: "No matches yet",
                            message: "Like people in Match. When they like you back, they show up here.",
                            systemImage: "face.smiling.inverse"
                        )
                    }
                }
                .padding(20)
            }
            .partyScreen()
            .navigationTitle(title)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") { dismiss() }
                }
            }
            .task {
                do { matches = try await model.api.matches() } catch { self.error = error.localizedDescription }
                loaded = true
            }
        }
    }

    private func pick(_ person: PublicProfile) {
        Task {
            do {
                try await onPick(person)
                withAnimation { _ = done.insert(person.id) }
            } catch {
                self.error = error.localizedDescription
            }
        }
    }
}
