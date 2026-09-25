// Who's in a chat. In a reunion chat, anyone can vote to remove someone,
// host included. Votes are anonymous: everyone sees the count, nobody sees
// who voted.

import SwiftUI

struct ChatMembersView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss

    let chat: Chat
    /// Called after you leave, so the chat screen can close too.
    var onLeft: () -> Void = {}

    @State private var members: [ChatMember] = []
    @State private var confirmingLeave = false
    @State private var votingAgainst: ChatMember?
    @State private var viewing: PersonRef?
    @State private var error: String?

    private var isReunion: Bool { chat.kind == "reunion" }
    private var myId: UUID? { model.me?.id }
    private var iAmHost: Bool { members.contains { $0.user.id == myId && $0.isHost } }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    if isReunion {
                        Text("Nobody runs a reunion chat. If most of the group votes someone out, "
                            + "they're out. Votes are anonymous.")
                            .font(.footnote)
                            .foregroundStyle(Theme.textDim)
                    }
                    ErrorText(text: error)

                    ForEach(members) { member in
                        MemberRow(
                            member: member,
                            isMe: member.user.id == myId,
                            canVote: isReunion && member.votesNeeded > 0
                        ) {
                            if member.iVoted { takeBack(member) } else { votingAgainst = member }
                        }
                        .contentShape(.rect)
                        .onTapGesture {
                            if member.user.id != myId { viewing = PersonRef(id: member.user.id) }
                        }
                    }

                    if !(chat.kind == "planning" && iAmHost) {
                        Button("Leave chat") { confirmingLeave = true }
                            .buttonStyle(.soft(Theme.pink))
                            .frame(maxWidth: .infinity)
                            .padding(.top, 12)
                    }
                }
                .padding(20)
            }
            .partyScreen()
            .navigationTitle("\(members.count) here")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } }
            }
            .confirmationDialog("Leave this chat?", isPresented: $confirmingLeave, titleVisibility: .visible) {
                Button("Leave", role: .destructive, action: leave)
            }
            .confirmationDialog(
                "Vote \(votingAgainst?.user.firstName ?? "them") out?",
                isPresented: Binding(get: { votingAgainst != nil }, set: { if !$0 { votingAgainst = nil } }),
                titleVisibility: .visible,
                presenting: votingAgainst
            ) { member in
                Button("Vote them out", role: .destructive) { vote(against: member) }
            } message: { member in
                Text("Nobody will know it was you. If \(member.votesNeeded) people vote, "
                    + "\(member.user.firstName ?? "they")'s out of the chat for good.")
            }
            .task { await load() }
            .personSheet($viewing)
        }
    }

    private func load() async {
        do { members = try await model.api.members(of: chat.id) } catch {
            self.error = error.localizedDescription
        }
    }

    private func vote(against member: ChatMember) {
        Task {
            do {
                _ = try await model.api.voteToRemove(member.user.id, from: chat.id)
                await load()
            } catch {
                self.error = error.localizedDescription
            }
        }
    }

    private func takeBack(_ member: ChatMember) {
        Task {
            do {
                try await model.api.takeBackVote(against: member.user.id, in: chat.id)
                await load()
            } catch {
                self.error = error.localizedDescription
            }
        }
    }

    private func leave() {
        Task {
            do {
                try await model.api.leave(chat.id)
                dismiss()
                onLeft()
            } catch {
                self.error = error.localizedDescription
            }
        }
    }
}

struct MemberRow: View {
    let member: ChatMember
    let isMe: Bool
    let canVote: Bool
    let onVote: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 12) {
                Avatar(url: member.user.photoUrl, name: member.user.firstName, size: 40)
                VStack(alignment: .leading, spacing: 2) {
                    HStack(spacing: 6) {
                        Text(isMe ? "You" : member.user.firstName ?? "Someone").font(.headline)
                        if member.isHost {
                            Badge(text: "host", systemImage: "crown.fill", color: Theme.yellow)
                        }
                    }
                    if member.votesToRemove > 0 {
                        Text("\(member.votesToRemove) of \(member.votesNeeded) votes to remove")
                            .font(.caption.weight(.bold))
                            .foregroundStyle(Theme.pink)
                    }
                }
                Spacer()
                if canVote && !isMe {
                    if member.iVoted {
                        Button("Take back", action: onVote).buttonStyle(.soft(Theme.textDim))
                    } else {
                        Button("Vote out", action: onVote).buttonStyle(.soft(Theme.pink))
                    }
                }
            }
            if member.votesToRemove > 0 && member.votesNeeded > 0 {
                // How close the vote is, as a bar.
                ProgressView(value: Double(member.votesToRemove), total: Double(member.votesNeeded))
                    .tint(Theme.pink)
            }
        }
        .card(padding: 14)
    }
}
