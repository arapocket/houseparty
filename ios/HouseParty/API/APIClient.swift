// Every call to the server goes through here.
//
// One generic `send` does the work: build the request, attach the token,
// encode the body, check the status code, decode the answer. The named
// methods further down (`discover()`, `like(_:)`, ...) are one line each on
// top of it, so the whole API is readable at a glance.

import Foundation

enum APIError: LocalizedError {
    /// No token, or it expired. The app should go back to sign-in.
    case signedOut
    /// Signed in, but the profile isn't finished yet (the server says 428).
    case needsOnboarding
    /// The server said no, with a plain-English reason we can show as is.
    case rejected(status: Int, message: String)
    /// Couldn't reach the server at all.
    case offline

    var errorDescription: String? {
        switch self {
        case .signedOut: "Please sign in again."
        case .needsOnboarding: "Finish your profile first."
        case .rejected(_, let message): message
        case .offline: "Can't reach House Party. Check your connection."
        }
    }
}

struct APIClient: Sendable {
    /// The simulator can reach the Mac's localhost directly.
    static let defaultBaseURL = URL(string: "http://localhost:8000")!

    var baseURL: URL = APIClient.defaultBaseURL
    var token: String?

    // MARK: JSON settings shared by every call

    static let decoder: JSONDecoder = {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        decoder.dateDecodingStrategy = .custom { decoder in
            let text = try decoder.singleValueContainer().decode(String.self)
            // The server sends "2026-09-25T05:43:53.206535Z", sometimes
            // without the fraction. This style reads both.
            let style = Date.ISO8601FormatStyle(includingFractionalSeconds: true)
            if let date = try? style.parse(text) {
                return date
            }
            throw DecodingError.dataCorrupted(
                .init(codingPath: decoder.codingPath, debugDescription: "Bad date: \(text)")
            )
        }
        return decoder
    }()

    static let encoder: JSONEncoder = {
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        encoder.dateEncodingStrategy = .iso8601  // includes the timezone, which the server requires
        return encoder
    }()

    // MARK: The one function that talks to the server

    func send<Response: Decodable>(
        _ method: String,
        _ path: String,
        body: (any Encodable)? = nil,
        query: [String: String] = [:]
    ) async throws -> Response {
        var components = URLComponents(
            url: baseURL.appending(path: path), resolvingAgainstBaseURL: false
        )!
        if !query.isEmpty {
            components.queryItems = query.map { URLQueryItem(name: $0.key, value: $0.value) }
        }

        var request = URLRequest(url: components.url!)
        request.httpMethod = method
        if let token {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        if let body {
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try Self.encoder.encode(body)
        }

        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await URLSession.shared.data(for: request)
        } catch {
            throw APIError.offline
        }

        let status = (response as? HTTPURLResponse)?.statusCode ?? 0
        switch status {
        case 200..<300:
            // DELETE /me answers 204 with nothing in it.
            if Response.self == OK.self, data.isEmpty {
                return OK(ok: true) as! Response
            }
            return try Self.decoder.decode(Response.self, from: data)
        case 401:
            throw APIError.signedOut
        case 428:
            throw APIError.needsOnboarding
        default:
            throw APIError.rejected(status: status, message: Self.message(from: data))
        }
    }

    /// Errors come back as {"detail": "some sentence"}, or for bad input as
    /// {"detail": [{"msg": "..."}, ...]}. Either way, find the words.
    static func message(from data: Data) -> String {
        struct Sentence: Decodable { let detail: String }
        struct Problems: Decodable {
            struct Problem: Decodable { let msg: String }
            let detail: [Problem]
        }
        if let sentence = try? JSONDecoder().decode(Sentence.self, from: data) {
            return sentence.detail
        }
        if let problems = try? JSONDecoder().decode(Problems.self, from: data),
           let first = problems.detail.first {
            // Pydantic prefixes its messages with "Value error, ".
            return first.msg.replacingOccurrences(of: "Value error, ", with: "")
        }
        return "Something went wrong."
    }
}

// MARK: - Every endpoint

extension APIClient {
    // Sign in
    func startPhone(_ phone: String) async throws {
        let _: OK = try await send("POST", "auth/phone/start", body: PhoneStart(phone: phone))
    }

    func verifyPhone(_ phone: String, code: String) async throws -> TokenResponse {
        try await send("POST", "auth/phone/verify", body: PhoneVerify(phone: phone, code: code))
    }

    // Profile
    func me() async throws -> Me { try await send("GET", "me") }

    func updateProfile(_ changes: ProfileUpdate) async throws -> Me {
        try await send("PATCH", "me", body: changes)
    }

    func setInterests(_ interests: [String]) async throws -> Me {
        try await send("PUT", "me/interests", body: InterestsUpdate(interests: interests))
    }

    /// Photos go up as a multipart form, the standard way browsers upload
    /// files, rather than JSON.
    func uploadPhoto(jpeg: Data) async throws -> PhotoResult {
        let boundary = "HouseParty-\(UUID().uuidString)"
        var body = Data()
        body.append(Data("--\(boundary)\r\n".utf8))
        body.append(Data("Content-Disposition: form-data; name=\"photo\"; filename=\"photo.jpg\"\r\n".utf8))
        body.append(Data("Content-Type: image/jpeg\r\n\r\n".utf8))
        body.append(jpeg)
        body.append(Data("\r\n--\(boundary)--\r\n".utf8))

        var request = URLRequest(url: baseURL.appending(path: "me/photo"))
        request.httpMethod = "POST"
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        if let token { request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization") }
        request.httpBody = body

        let (data, response): (Data, URLResponse)
        do { (data, response) = try await URLSession.shared.data(for: request) } catch {
            throw APIError.offline
        }
        let status = (response as? HTTPURLResponse)?.statusCode ?? 0
        guard status == 200 else {
            if status == 401 { throw APIError.signedOut }
            throw APIError.rejected(status: status, message: Self.message(from: data))
        }
        return try Self.decoder.decode(PhotoResult.self, from: data)
    }

    func deleteAccount() async throws {
        let _: OK = try await send("DELETE", "me")
    }

    func profile(_ userId: UUID) async throws -> PublicProfile {
        try await send("GET", "users/\(userId)")
    }

    func suggestInterests(_ text: String) async throws -> [InterestSuggestion] {
        try await send("GET", "interests/suggest", query: ["q": text])
    }

    // Discover and matches
    func discover(offset: Int = 0) async throws -> [DiscoverCard] {
        try await send("GET", "discover", query: ["offset": String(offset)])
    }

    func passed() async throws -> [PassedPerson] { try await send("GET", "discover/passed") }

    func like(_ userId: UUID) async throws -> DecisionResult {
        try await send("POST", "discover/\(userId)/decision", body: Decision(decision: "like"))
    }

    func pass(_ userId: UUID) async throws -> DecisionResult {
        try await send("POST", "discover/\(userId)/decision", body: Decision(decision: "pass"))
    }

    func matches() async throws -> [MatchRow] { try await send("GET", "matches") }

    // Parties
    func myParties() async throws -> [Party] { try await send("GET", "parties") }

    func party(_ id: UUID) async throws -> Party { try await send("GET", "parties/\(id)") }

    func createParty(_ party: NewParty) async throws -> Party {
        try await send("POST", "parties", body: party)
    }

    func updateParty(_ id: UUID, _ changes: PartyChanges) async throws -> Party {
        try await send("PATCH", "parties/\(id)", body: changes)
    }

    func myFeedback(for partyId: UUID) async throws -> MyFeedback {
        try await send("GET", "parties/\(partyId)/feedback")
    }

    func cancelParty(_ id: UUID) async throws -> Party {
        try await send("POST", "parties/\(id)/cancel")
    }

    func guests(of partyId: UUID) async throws -> [Guest] {
        try await send("GET", "parties/\(partyId)/guests")
    }

    func invite(_ userId: UUID, to partyId: UUID) async throws -> Invite {
        try await send("POST", "parties/\(partyId)/invites", body: UserRef(userId: userId))
    }

    func removeGuest(inviteId: UUID, from partyId: UUID) async throws {
        let _: OK = try await send("DELETE", "parties/\(partyId)/invites/\(inviteId)")
    }

    func suggest(_ userId: UUID, for partyId: UUID) async throws {
        let _: OK = try await send(
            "POST", "parties/\(partyId)/suggestions", body: UserRef(userId: userId)
        )
    }

    func askForBiggerParty(_ partyId: UUID, cap: Int, reason: String?) async throws {
        let _: OK = try await send(
            "POST", "parties/\(partyId)/bigger", body: BiggerParty(requestedCap: cap, reason: reason)
        )
    }

    func leaveFeedback(_ partyId: UUID, about userId: UUID, again: Bool) async throws {
        let body = Feedback(userId: userId, wouldPartyAgain: again, note: nil)
        let _: OK = try await send("POST", "parties/\(partyId)/feedback", body: body)
    }

    // Invites
    func invites() async throws -> [Invite] { try await send("GET", "invites") }

    func answer(_ inviteId: UUID, accept: Bool) async throws -> Invite {
        try await send("POST", "invites/\(inviteId)/respond", body: InviteAnswer(accept: accept))
    }

    // Chat
    func chats() async throws -> [Chat] { try await send("GET", "chats") }

    func messages(in chatId: UUID) async throws -> [Message] {
        try await send("GET", "chats/\(chatId)/messages")
    }

    func sendMessage(_ text: String, to chatId: UUID) async throws -> Message {
        try await send("POST", "chats/\(chatId)/messages", body: NewMessage(body: text))
    }

    func members(of chatId: UUID) async throws -> [ChatMember] {
        try await send("GET", "chats/\(chatId)/members")
    }

    func join(_ chatId: UUID) async throws -> Chat { try await send("POST", "chats/\(chatId)/join") }

    func leave(_ chatId: UUID) async throws {
        let _: OK = try await send("POST", "chats/\(chatId)/leave")
    }

    func voteToRemove(_ userId: UUID, from chatId: UUID) async throws -> KickVoteResult {
        try await send("POST", "chats/\(chatId)/kick-votes", body: UserRef(userId: userId))
    }

    func takeBackVote(against userId: UUID, in chatId: UUID) async throws {
        let _: OK = try await send("DELETE", "chats/\(chatId)/kick-votes/\(userId)")
    }

    // Safety
    func report(_ report: NewReport) async throws {
        let _: OK = try await send("POST", "reports", body: report)
    }

    func block(_ userId: UUID) async throws {
        let _: OK = try await send("POST", "blocks", body: UserRef(userId: userId))
    }
}
