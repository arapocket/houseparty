// What the app sends to the server. Optional fields that are nil are left
// out of the JSON entirely, which is how PATCH knows "don't change this".

import Foundation

struct PhoneStart: Encodable {
    let phone: String
}

struct PhoneVerify: Encodable {
    let phone: String
    let code: String
}

struct ProfileUpdate: Encodable {
    var firstName: String?
    /// "1995-05-17". Can be set once and never changed.
    var birthdate: String?
    var bio: String?
    var neighborhood: String?
    var latitude: Double?
    var longitude: Double?
    var searchRadiusKm: Int?
    var downToParty: Bool?
}

struct InterestsUpdate: Encodable {
    let interests: [String]
}

struct Decision: Encodable {
    /// "like" or "pass"
    let decision: String
}

struct NewParty: Encodable {
    var title: String
    var description: String?
    var startsAt: Date
    var endsAt: Date?
    var neighborhood: String
    /// The pin the host drops. Required.
    var latitude: Double
    var longitude: Double
    var address: String?
    var interests: [String]
    var sourcePartyId: UUID?
}

struct UserRef: Encodable {
    let userId: UUID
}

struct InviteAnswer: Encodable {
    let accept: Bool
}

struct BiggerParty: Encodable {
    let requestedCap: Int
    let reason: String?
}

struct Feedback: Encodable {
    let userId: UUID
    let wouldPartyAgain: Bool
    let note: String?
}

struct NewMessage: Encodable {
    let body: String
}

struct NewReport: Encodable {
    var subjectUserId: UUID?
    var subjectPartyId: UUID?
    var subjectMessageId: UUID?
    let reason: String
    var note: String?
}

extension Date {
    /// The "1995-05-17" form the server wants for a birthdate.
    var birthdateString: String {
        formatted(.iso8601.year().month().day())
    }
}
