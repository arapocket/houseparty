// One conversation. Messages stream in live while the screen is open.
// Long-press a message to report it or block the person who sent it.

import SwiftUI

struct ChatView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss

    let chat: Chat

    @State private var messages: [Message] = []
    @State private var draft = ""
    @State private var sending = false
    @State private var showingMembers = false
    @State private var hostingAgain: Party?
    @State private var removed = false
    @State private var error: String?
    @State private var notice: String?

    private var myId: UUID? { model.me?.id }
    private var isReunion: Bool { chat.kind == "reunion" }

    var body: some View {
        VStack(spacing: 0) {
            ScrollView {
                LazyVStack(spacing: 6) {
                    if isReunion {
                        HostAgainBanner { startHostAgain() }
                            .padding(.bottom, 10)
                    }
                    if messages.isEmpty {
                        Text(isReunion ? "The party happened. Say something." : "Plan the party here.")
                            .font(.subheadline)
                            .foregroundStyle(Theme.textDim)
                            .padding(.top, 40)
                    }
                    ForEach(Array(messages.enumerated()), id: \.element.id) { index, message in
                        let mine = message.senderId == myId
                        let firstInRun = index == 0 || messages[index - 1].senderId != message.senderId
                        Bubble(message: message, mine: mine, showName: firstInRun && !mine)
                            .padding(.top, firstInRun ? 8 : 0)
                            .contextMenu {
                                if !mine { safetyMenu(for: message) }
                            }
                            .id(message.id)
                    }
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 12)
            }
            .defaultScrollAnchor(.bottom)
            .scrollDismissesKeyboard(.interactively)

            if let notice {
                Text(notice)
                    .font(.footnote.weight(.semibold))
                    .foregroundStyle(Theme.mint)
                    .padding(.vertical, 6)
            }
            ErrorText(text: error).padding(.horizontal, 16)

            if removed {
                Text("You're no longer in this chat.")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(Theme.textDim)
                    .padding()
            } else {
                composer
            }
        }
        .partyScreen()
        .navigationTitle(chat.title ?? "Chat")
        .navigationBarTitleDisplayMode(.inline)
        .toolbarVisibility(.hidden, for: .tabBar)  // room for the message box
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button { showingMembers = true } label: {
                    Image(systemName: "person.2.fill")
                }
                .accessibilityLabel("People in this chat")
            }
        }
        .sheet(isPresented: $showingMembers) {
            ChatMembersView(chat: chat) {
                // Left the chat: close it.
                dismiss()
            }
        }
        .sheet(item: $hostingAgain) { party in
            NewPartyView(sourceParty: party)
        }
        .task { await loadHistory() }
        .task { await listen() }
    }

    private var composer: some View {
        HStack(alignment: .bottom, spacing: 10) {
            TextField("", text: $draft, prompt: Text("Message").foregroundStyle(Theme.textDim), axis: .vertical)
                .lineLimit(1...5)
                .padding(.horizontal, 16)
                .padding(.vertical, 12)
                .background(Theme.surfaceHigh, in: .rect(cornerRadius: Theme.corner))
                .overlay(RoundedRectangle(cornerRadius: Theme.corner).stroke(Theme.stroke))
            Button(action: send) {
                Image(systemName: "arrow.up")
                    .font(.headline.weight(.heavy))
                    .foregroundStyle(.white)
                    .frame(width: 44, height: 44)
                    .background(Theme.hot, in: .circle)
                    .shadow(color: Theme.pink.opacity(0.5), radius: 10)
            }
            .disabled(draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || sending)
            .opacity(draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? 0.4 : 1)
            .accessibilityLabel("Send")
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 10)
        .background(Theme.background.opacity(0.85))
    }

    @ViewBuilder
    private func safetyMenu(for message: Message) -> some View {
        Button {
            act("Reported. Thanks for telling us.") {
                try await model.api.report(NewReport(subjectMessageId: message.id, reason: "message"))
            }
        } label: {
            Label("Report message", systemImage: "flag")
        }
        if let senderId = message.senderId {
            Button(role: .destructive) {
                act("Blocked. You won't see each other anymore.") {
                    try await model.api.block(senderId)
                    messages.removeAll { $0.senderId == senderId }
                }
            } label: {
                Label("Block \(message.senderName ?? "them")", systemImage: "hand.raised")
            }
        }
    }

    // MARK: Actions

    private func loadHistory() async {
        do {
            let history = try await model.api.messages(in: chat.id)
            // Keep anything that arrived live while history was loading.
            let live = messages.filter { m in !history.contains { $0.id == m.id } }
            messages = history + live
        } catch APIError.rejected(status: 404, _) {
            removed = true
        } catch {
            self.error = error.localizedDescription
        }
    }

    private func listen() async {
        for await event in ChatSocket.events(chatId: chat.id, api: model.api) {
            switch event {
            case .message(let message):
                add(message)
            case .removed:
                removed = true
            }
        }
    }

    private func add(_ message: Message) {
        // The server echoes our own messages back; don't show them twice.
        guard !messages.contains(where: { $0.id == message.id }) else { return }
        withAnimation(.snappy) { messages.append(message) }
    }

    private func send() {
        let text = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        sending = true
        draft = ""
        Task {
            defer { sending = false }
            do {
                add(try await model.api.sendMessage(text, to: chat.id))
                error = nil
            } catch {
                draft = text  // give them their words back
                self.error = error.localizedDescription
            }
        }
    }

    private func startHostAgain() {
        Task {
            do { hostingAgain = try await model.api.party(chat.partyId) } catch {
                self.error = error.localizedDescription
            }
        }
    }

    private func act(_ done: String, _ work: @escaping () async throws -> Void) {
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

struct Bubble: View {
    let message: Message
    let mine: Bool
    let showName: Bool

    var body: some View {
        HStack {
            if mine { Spacer(minLength: 60) }
            VStack(alignment: mine ? .trailing : .leading, spacing: 3) {
                if showName, let name = message.senderName {
                    Text(name)
                        .font(.caption.weight(.bold))
                        .foregroundStyle(Theme.color(for: name))
                        .padding(.leading, 12)
                }
                Text(message.body)
                    .padding(.horizontal, 14)
                    .padding(.vertical, 10)
                    .foregroundStyle(mine ? .white : Theme.text)
                    .background(
                        mine ? AnyShapeStyle(Theme.hot) : AnyShapeStyle(Theme.surfaceHigh),
                        in: .rect(cornerRadius: Theme.corner)
                    )
            }
            if !mine { Spacer(minLength: 60) }
        }
    }
}

/// Top of every reunion chat: throw the next one with the same crowd.
struct HostAgainBanner: View {
    let action: () -> Void

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: "arrow.clockwise.circle.fill")
                .font(.title2)
                .foregroundStyle(Theme.hot)
            VStack(alignment: .leading, spacing: 2) {
                Text("Do it again?").font(.headline)
                Text("Start a new party with the same vibe.")
                    .font(.footnote)
                    .foregroundStyle(Theme.textDim)
            }
            Spacer()
            Button("Host again", action: action).buttonStyle(.soft(Theme.pink))
        }
        .card(padding: 14)
    }
}
