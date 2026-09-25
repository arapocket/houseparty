// Your parties: invites waiting for an answer, what's coming up (hosting or
// going), and what's already happened.

import SwiftUI

struct PartiesView: View {
    @Environment(AppModel.self) private var model

    @State private var parties: [Party] = []
    /// party id -> my invite id, so a party can be answered from its page.
    @State private var inviteIds: [UUID: UUID] = [:]
    @State private var loaded = false
    @State private var creating = false
    @State private var error: String?

    private var waiting: [Party] {
        parties.filter { $0.myInviteStatus == "pending" && $0.status == "active" }
    }
    private var upcoming: [Party] {
        parties.filter {
            $0.status == "active" && ["host", "accepted"].contains($0.myInviteStatus ?? "")
        }
    }
    private var past: [Party] {
        parties.filter { $0.status != "active" }.reversed()
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    HStack(alignment: .firstTextBaseline) {
                        ScreenTitle(text: Self.title())
                        Button { creating = true } label: {
                            Label("Host", systemImage: "plus")
                        }
                        .buttonStyle(.soft(Theme.pink))
                    }

                    ErrorText(text: error)

                    group("You're invited", waiting, highlight: true)
                    group("Coming up", upcoming)
                    group("Past", past)

                    if loaded && parties.isEmpty {
                        EmptyState(
                            title: "No parties yet",
                            message: "Host one and invite your matches, or wait for an invite.",
                            systemImage: "party.popper.fill"
                        )
                        .padding(.top, 40)
                        Button("Host a party") { creating = true }
                            .buttonStyle(.hot)
                    }
                }
                .padding(20)
            }
            .partyScreen()
            .toolbarVisibility(.hidden, for: .navigationBar)
            .navigationDestination(for: UUID.self) { partyId in
                PartyDetailView(partyId: partyId, inviteId: inviteIds[partyId]) {
                    Task { await load() }
                }
            }
            .refreshable { await load() }
            .task { await load() }
            .sheet(isPresented: $creating) {
                NewPartyView { _ in Task { await load() } }
            }
        }
    }

    /// The weekend gets its own name.
    static func title(on date: Date = .now) -> String {
        switch Calendar.current.component(.weekday, from: date) {
        case 6: "Friday Rush"
        case 7: "Saturday Magic"
        case 1: "Sunday Scaries"
        default: "Parties"
        }
    }

    @ViewBuilder
    private func group(_ title: String, _ items: [Party], highlight: Bool = false) -> some View {
        if !items.isEmpty {
            VStack(alignment: .leading, spacing: 12) {
                SectionLabel(title)
                ForEach(items) { party in
                    NavigationLink(value: party.id) {
                        PartyRow(party: party, highlight: highlight)
                    }
                    .buttonStyle(.plain)
                }
            }
        }
    }

    private func load() async {
        do {
            async let partiesCall = model.api.myParties()
            async let invitesCall = model.api.invites()
            let (freshParties, invites) = try await (partiesCall, invitesCall)
            parties = freshParties
            inviteIds = Dictionary(invites.map { ($0.partyId, $0.id) }, uniquingKeysWith: { a, _ in a })
            error = nil
        } catch {
            self.error = error.localizedDescription
        }
        loaded = true
    }
}

struct PartyRow: View {
    let party: Party
    var highlight = false

    var body: some View {
        HStack(alignment: .top, spacing: 14) {
            DateBlock(date: party.startsAt, color: accent)
            VStack(alignment: .leading, spacing: 6) {
                Text(party.title)
                    .font(.headline)
                    .foregroundStyle(Theme.text)
                    .strikethrough(party.status == "cancelled")
                Text(subtitle)
                    .font(.subheadline)
                    .foregroundStyle(Theme.textDim)
                HStack(spacing: 6) {
                    ForEach(party.interests.prefix(3), id: \.self) { interest in
                        Circle().fill(Theme.color(for: interest)).frame(width: 8, height: 8)
                    }
                    Text(statusText)
                        .font(.caption.weight(.bold))
                        .foregroundStyle(accent)
                }
            }
            Spacer()
            Image(systemName: "chevron.right").foregroundStyle(Theme.textDim)
        }
        .card(padding: 14)
        .overlay(
            RoundedRectangle(cornerRadius: Theme.corner)
                .stroke(highlight ? AnyShapeStyle(Theme.hot) : AnyShapeStyle(.clear), lineWidth: 2)
        )
    }

    private var accent: Color {
        switch party.status {
        case "cancelled": Theme.textDim
        case "completed": Theme.violet
        default: highlight ? Theme.pink : Theme.color(for: party.interests.first ?? party.title)
        }
    }

    private var subtitle: String {
        var parts = [party.neighborhood]
        if let km = party.distanceKm { parts.append("\(km) km") }
        parts.append("hosted by \(party.myInviteStatus == "host" ? "you" : party.host.firstName ?? "someone")")
        return parts.joined(separator: " · ")
    }

    private var statusText: String {
        switch (party.status, party.myInviteStatus) {
        case ("cancelled", _): "Cancelled"
        case ("completed", _): "Happened"
        case (_, "pending"): "Waiting for your answer"
        case (_, "host"): "\(party.guestCount) going · \(party.invitesLeft) invites left"
        default: "You're going · \(party.guestCount) going"
        }
    }
}

/// The calendar-page date on the left of a party row.
struct DateBlock: View {
    let date: Date
    let color: Color

    var body: some View {
        VStack(spacing: 0) {
            Text(date.formatted(.dateTime.month(.abbreviated)).uppercased())
                .font(.caption2.weight(.heavy))
                .foregroundStyle(color)
            Text(date.formatted(.dateTime.day()))
                .font(.system(size: 26, weight: .heavy, design: Theme.fontDesign))
            Text(date.formatted(.dateTime.weekday(.abbreviated)))
                .font(.caption2)
                .foregroundStyle(Theme.textDim)
        }
        .frame(width: 56, height: 68)
        .background(color.opacity(0.14), in: .rect(cornerRadius: Theme.cornerSmall))
    }
}
