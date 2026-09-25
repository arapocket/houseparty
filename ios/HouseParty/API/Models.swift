// What the server sends back, written by hand to match backend/app/schemas.py.
//
// The server uses snake_case ("first_name"); the decoder in APIClient turns
// that into Swift's camelCase ("firstName") automatically, so the names here
// line up with the Python field names one to one.

import Foundation

// MARK: - Auth

struct TokenResponse: Decodable {
    let accessToken: String
    let needsOnboarding: Bool
}

// MARK: - People

/// Someone else, as the app is allowed to see them. No phone, no exact location.
struct PublicProfile: Decodable, Identifiable, Hashable {
    let id: UUID
    let firstName: String?
    let age: Int?
    let bio: String?
    let photoUrl: String?
    let neighborhood: String?
    let downToParty: Bool
    let interests: [String]
}

/// Your own profile: everything public plus your settings.
struct Me: Decodable {
    let id: UUID
    let firstName: String?
    let age: Int?
    let bio: String?
    let photoUrl: String?
    let neighborhood: String?
    let downToParty: Bool
    let interests: [String]
    let phone: String
    let searchRadiusKm: Int
    let inviteCap: Int
    let needsOnboarding: Bool
    /// A new photo is waiting for a person to check it.
    let photoInReview: Bool
}

struct PhotoResult: Decodable {
    /// False when the automatic check held it back for review.
    let live: Bool
    let me: Me
}

struct InterestSuggestion: Decodable, Hashable {
    let display: String
    let usageCount: Int
}

// MARK: - Discover and matches

struct DiscoverCard: Decodable, Identifiable {
    let user: PublicProfile
    let sharedInterests: [String]
    let distanceKm: Int
    /// Set when a guest introduced you two for one of their parties.
    let suggestedForPartyId: UUID?

    var id: UUID { user.id }
}

struct PassedPerson: Decodable, Identifiable {
    let user: PublicProfile
    let sharedInterests: [String]
    let passedAt: Date

    var id: UUID { user.id }
}

struct DecisionResult: Decodable {
    let matched: Bool
    let matchId: UUID?
}

struct MatchRow: Decodable, Identifiable {
    let user: PublicProfile
    let matchedAt: Date
    let sharedInterests: [String]

    var id: UUID { user.id }
}

// MARK: - Parties

struct Party: Decodable, Identifiable {
    let id: UUID
    let title: String
    let description: String?
    let startsAt: Date
    let endsAt: Date?
    let neighborhood: String
    /// "active", "cancelled" or "completed"
    let status: String
    let interests: [String]
    let host: PublicProfile
    let guestCount: Int
    let guestCap: Int
    let invitesLeft: Int
    let distanceKm: Int?
    /// Only filled in once you've accepted, or if you're the host.
    let address: String?
    /// "host", "pending", "accepted", "declined", or nil
    let myInviteStatus: String?
    let guests: [PublicProfile]
    /// The exact pin. Only sent to the host.
    let latitude: Double?
    let longitude: Double?
}

struct MyFeedback: Decodable {
    /// Person id (as text) -> would you party with them again.
    let answers: [String: Bool]
}

/// The host's view of one invite.
struct Guest: Decodable, Identifiable {
    let inviteId: UUID
    let user: PublicProfile
    let status: String

    var id: UUID { inviteId }
}

struct Invite: Decodable, Identifiable {
    let id: UUID
    let partyId: UUID
    let status: String
    let createdAt: Date
    let party: Party?
}

// MARK: - Chat

struct Chat: Decodable, Identifiable {
    let id: UUID
    let partyId: UUID
    /// "planning" (the host's) or "reunion" (after the party, opt-in)
    let kind: String
    let title: String?
    let memberCount: Int
    let joined: Bool
    let canJoin: Bool
    let lastMessage: String?
    let lastMessageAt: Date?
    let lastSenderName: String?
}

struct ChatMember: Decodable, Identifiable {
    let user: PublicProfile
    let isHost: Bool
    /// Reunion chats only. Anonymous: a count, never who voted.
    let votesToRemove: Int
    let votesNeeded: Int
    let iVoted: Bool

    var id: UUID { user.id }
}

struct Message: Decodable, Identifiable, Hashable {
    let id: UUID
    let chatId: UUID
    let senderId: UUID?
    let senderName: String?
    let body: String
    let createdAt: Date
}

struct KickVoteResult: Decodable {
    let votes: Int
    let votesNeeded: Int
    let removed: Bool
}

/// For endpoints that only answer {"ok": true}.
struct OK: Decodable {
    let ok: Bool
}
