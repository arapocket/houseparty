// The live connection for one chat. While a chat screen is open, new
// messages arrive here the moment anyone sends one.
//
// Sending still goes through the normal POST in APIClient, which gives a
// clear error if something's wrong. The server then pushes the message to
// everyone connected, including the sender, so the chat screen ignores
// messages it already has.

import Foundation

enum ChatEvent: Sendable {
    case message(Message)
    /// The server hung up because you were removed from the chat.
    case removed
}

enum ChatSocket {
    /// Streams events until the screen closes (the calling task is cancelled)
    /// or the connection drops.
    static func events(chatId: UUID, api: APIClient) -> AsyncStream<ChatEvent> {
        AsyncStream { continuation in
            var components = URLComponents(
                url: api.baseURL.appending(path: "chats/\(chatId)/ws"),
                resolvingAgainstBaseURL: false
            )!
            components.scheme = api.baseURL.scheme == "https" ? "wss" : "ws"
            var request = URLRequest(url: components.url!)
            if let token = api.token {
                request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
            }

            let socket = URLSession.shared.webSocketTask(with: request)
            socket.resume()

            let reader = Task {
                while !Task.isCancelled {
                    guard let incoming = try? await socket.receive() else { break }
                    if let event = decode(incoming) { continuation.yield(event) }
                }
                // 4403 is the server's "you were removed from this chat".
                if socket.closeCode.rawValue == 4403 { continuation.yield(.removed) }
                continuation.finish()
            }

            continuation.onTermination = { _ in
                reader.cancel()
                socket.cancel(with: .goingAway, reason: nil)
            }
        }
    }

    /// The server sends {"type": "message", "message": {...}} for new
    /// messages. Anything else is ignored.
    private static func decode(_ incoming: URLSessionWebSocketTask.Message) -> ChatEvent? {
        struct Envelope: Decodable {
            let type: String
            let message: Message?
        }
        let data: Data
        switch incoming {
        case .string(let text): data = Data(text.utf8)
        case .data(let bytes): data = bytes
        @unknown default: return nil
        }
        guard let envelope = try? APIClient.decoder.decode(Envelope.self, from: data),
              envelope.type == "message",
              let message = envelope.message
        else { return nil }
        return .message(message)
    }
}
