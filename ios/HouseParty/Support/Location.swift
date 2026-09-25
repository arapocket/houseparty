// Getting the phone's location once, for your profile and for Discover.
//
// The exact spot is sent to the server and never shown to anyone; other
// people only ever see a distance rounded to the nearest kilometre.

import CoreLocation

enum Location {
    enum Problem: LocalizedError {
        case denied
        case unavailable

        var errorDescription: String? {
            switch self {
            case .denied:
                "House Party needs your location to find people nearby. "
                    + "Turn it on in Settings > Privacy > Location Services."
            case .unavailable:
                "Couldn't find your location. Try again in a moment."
            }
        }
    }

    /// Asks for permission if needed, then waits for the first good fix.
    static func current() async throws -> CLLocationCoordinate2D {
        // Keep the session alive while we wait; it's what shows the
        // permission prompt.
        let session = CLServiceSession(authorization: .whenInUse)
        defer { session.invalidate() }

        for try await update in CLLocationUpdate.liveUpdates() {
            if update.authorizationDenied || update.authorizationDeniedGlobally {
                throw Problem.denied
            }
            if let location = update.location {
                return location.coordinate
            }
        }
        throw Problem.unavailable
    }
}
