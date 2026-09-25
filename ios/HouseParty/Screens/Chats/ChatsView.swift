// Every chat you're in: the planning chat for each party you're hosting or
// going to, and reunion chats after parties you were at (join them here).

import SwiftUI

struct ChatsView: View {
    @Environment(AppModel.self) private var model

    @State private var chats: [Chat] = []
    @State private var loaded = false
    @State private var error: String?

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    ScreenTitle(text: "Chats")
                    ErrorText(text: error)

                    let joinable = chats.filter(\.canJoin)
                    if !joinable.isEmpty {
                        SectionLabel("Reunions you can join")
                        ForEach(joinable) { chat in
                            JoinReunionRow(chat: chat) { join(chat) }
                        }
                    }

                    let mine = chats.filter(\.joined)
                    if !mine.isEmpty {
                        if !joinable.isEmpty { SectionLabel("Your chats").padding(.top, 8) }
                        ForEach(mine) { chat in
                            NavigationLink(value: chat.id) {
                                ChatRow(chat: chat)
                            }
                            .buttonStyle(.plain)
                        }
                    }

                    if loaded && chats.isEmpty {
                        EmptyState(
                            title: "No chats yet",
                            message: "Every party gets a chat. Host one or say yes to an invite.",
                            systemImage: "bubble.left.and.bubble.right.fill"
                        )
                        .padding(.top, 60)
                    }
                }
                .padding(20)
            }
            .partyScreen()
            .toolbarVisibility(.hidden, for: .navigationBar)
            .navigationDestination(for: UUID.self) { chatId in
                if let chat = chats.first(where: { $0.id == chatId }) {
                    ChatView(chat: chat)
                }
            }
            .refreshable { await load() }
            // Reload every time the tab appears, so previews stay current.
            .onAppear { Task { await load() } }
        }
    }

    private func load() async {
        do {
            chats = try await model.api.chats()
            error = nil
        } catch {
            self.error = error.localizedDescription
        }
        loaded = true
    }

    private func join(_ chat: Chat) {
        Task {
            do {
                _ = try await model.api.join(chat.id)
                await load()
            } catch {
                self.error = error.localizedDescription
            }
        }
    }
}

struct ChatRow: View {
    let chat: Chat

    var body: some View {
        HStack(spacing: 14) {
            ChatIcon(kind: chat.kind)
            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Text(chat.title ?? "Party chat")
                        .font(.headline)
                        .foregroundStyle(Theme.text)
                        .lineLimit(1)
                    Spacer()
                    if let at = chat.lastMessageAt {
                        Text(at, format: .relative(presentation: .numeric, unitsStyle: .narrow))
                            .font(.caption)
                            .foregroundStyle(Theme.textDim)
                    }
                }
                Text(preview)
                    .font(.subheadline)
                    .foregroundStyle(Theme.textDim)
                    .lineLimit(2)
            }
        }
        .card(padding: 14)
    }

    private var preview: String {
        guard let message = chat.lastMessage else {
            return chat.kind == "reunion" ? "Reunion · \(chat.memberCount) here" : "Say hi to the group"
        }
        if let name = chat.lastSenderName { return "\(name): \(message)" }
        return message
    }
}

struct JoinReunionRow: View {
    let chat: Chat
    let onJoin: () -> Void

    var body: some View {
        HStack(spacing: 14) {
            ChatIcon(kind: "reunion")
            VStack(alignment: .leading, spacing: 4) {
                Text(chat.title ?? "Reunion").font(.headline)
                Text("The party's over. Keep the group going?")
                    .font(.subheadline)
                    .foregroundStyle(Theme.textDim)
            }
            Spacer()
            Button("Join", action: onJoin).buttonStyle(.soft(Theme.violet))
        }
        .card(padding: 14)
        .overlay(RoundedRectangle(cornerRadius: Theme.corner).stroke(Theme.violet.opacity(0.6), lineWidth: 1.5))
    }
}

/// Planning chats are pink-blue (it's happening); reunions are violet
/// (it happened).
struct ChatIcon: View {
    let kind: String

    var body: some View {
        let reunion = kind == "reunion"
        Image(systemName: reunion ? "sparkles" : "party.popper.fill")
            .font(.title3)
            .foregroundStyle(.white)
            .frame(width: 48, height: 48)
            .background(
                reunion
                    ? AnyShapeStyle(LinearGradient(colors: [Theme.violet, Theme.cyan], startPoint: .topLeading, endPoint: .bottomTrailing))
                    : AnyShapeStyle(Theme.hot),
                in: .rect(cornerRadius: Theme.cornerSmall)
            )
    }
}
