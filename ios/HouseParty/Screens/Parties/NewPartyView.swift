// Hosting a party: what, when, which interests it's for, and a pin on the
// map for where. Guests only see the neighborhood and a rounded distance
// until they accept.

import MapKit
import SwiftUI

struct NewPartyView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss

    /// Set by "Host again": the party this one follows on from.
    var sourceParty: Party? = nil
    /// Called with the new party once it's saved.
    var onCreated: (Party) -> Void = { _ in }

    @State private var title = ""
    @State private var description = ""
    @State private var startsAt = NewPartyView.nextSaturdayEvening()
    @State private var hasEnd = false
    @State private var endsAt = NewPartyView.nextSaturdayEvening().addingTimeInterval(4 * 3600)
    @State private var neighborhood = ""
    @State private var address = ""
    @State private var interests: [String] = []
    @State private var pin: CLLocationCoordinate2D?
    @State private var working = false
    @State private var error: String?

    private var ready: Bool {
        !title.isEmpty && !neighborhood.isEmpty && !interests.isEmpty && pin != nil
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    VStack(alignment: .leading, spacing: 12) {
                        SectionLabel("The party")
                        TextField("", text: $title, prompt: Text("Kid A front to back").foregroundStyle(Theme.textDim))
                            .font(.title3.weight(.bold))
                            .fieldStyle()
                        TextField(
                            "", text: $description,
                            prompt: Text("What's the plan? Bring anything?").foregroundStyle(Theme.textDim),
                            axis: .vertical
                        )
                        .lineLimit(3...6)
                        .fieldStyle()
                    }

                    VStack(alignment: .leading, spacing: 12) {
                        SectionLabel("When")
                        DatePicker("Starts", selection: $startsAt, in: Date.now...)
                        Toggle("Set an end time", isOn: $hasEnd.animation())
                        if hasEnd {
                            DatePicker("Ends", selection: $endsAt, in: startsAt...)
                        }
                    }
                    .card()

                    VStack(alignment: .leading, spacing: 12) {
                        SectionLabel("It's for people into")
                        InterestsEditor(interests: $interests, limit: 5)
                    }
                    .card()

                    VStack(alignment: .leading, spacing: 12) {
                        SectionLabel("Where")
                        Text("Tap the map to drop the pin. Guests only see how far away it is until they say yes.")
                            .font(.footnote)
                            .foregroundStyle(Theme.textDim)
                        PinPicker(pin: $pin)
                            .frame(height: 240)
                            .clipShape(.rect(cornerRadius: Theme.corner))
                        TextField("", text: $neighborhood, prompt: Text("Neighborhood (everyone sees this)").foregroundStyle(Theme.textDim))
                            .fieldStyle()
                        TextField("", text: $address, prompt: Text("Apt, buzzer… (only for guests who say yes)").foregroundStyle(Theme.textDim))
                            .fieldStyle()
                    }
                    .card()

                    ErrorText(text: error)

                    Button("Create party", action: create)
                        .buttonStyle(.hot)
                        .disabled(!ready || working)
                }
                .padding(20)
            }
            .scrollDismissesKeyboard(.interactively)
            .partyScreen()
            .navigationTitle(sourceParty == nil ? "Host a party" : "Host again")
            .onAppear(perform: prefill)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
            }
        }
    }

    /// "Host again" starts from the old party: same name and interests,
    /// new date and pin.
    private func prefill() {
        guard let sourceParty, title.isEmpty else { return }
        title = sourceParty.title
        description = sourceParty.description ?? ""
        neighborhood = sourceParty.neighborhood
        interests = sourceParty.interests
    }

    private func create() {
        guard let pin else { return }
        working = true
        error = nil
        Task {
            defer { working = false }
            do {
                let party = try await model.api.createParty(NewParty(
                    title: title,
                    description: description.isEmpty ? nil : description,
                    startsAt: startsAt,
                    endsAt: hasEnd ? endsAt : nil,
                    neighborhood: neighborhood,
                    latitude: pin.latitude,
                    longitude: pin.longitude,
                    address: address.isEmpty ? nil : address,
                    interests: interests,
                    sourcePartyId: sourceParty?.id
                ))
                onCreated(party)
                dismiss()
            } catch {
                self.error = error.localizedDescription
            }
        }
    }

    /// A sensible default: this coming Saturday at 8pm.
    static func nextSaturdayEvening() -> Date {
        let calendar = Calendar.current
        let saturday = calendar.nextDate(
            after: .now, matching: DateComponents(hour: 20, weekday: 7), matchingPolicy: .nextTime
        )
        return saturday ?? .now.addingTimeInterval(3 * 86400)
    }
}

/// A map you tap to place the party's pin. Starts at your own location.
struct PinPicker: View {
    @Binding var pin: CLLocationCoordinate2D?
    @State private var camera: MapCameraPosition = .userLocation(fallback: .automatic)

    var body: some View {
        MapReader { proxy in
            Map(position: $camera) {
                UserAnnotation()
                if let pin {
                    Annotation("Party", coordinate: pin) {
                        Image(systemName: "party.popper.fill")
                            .font(.title3)
                            .foregroundStyle(.white)
                            .padding(10)
                            .background(Theme.hot, in: .circle)
                            .shadow(color: Theme.pink.opacity(0.7), radius: 10)
                    }
                }
            }
            .mapStyle(.standard(pointsOfInterest: .excludingAll))
            .onTapGesture { point in
                if let coordinate = proxy.convert(point, from: .local) {
                    withAnimation(.snappy) { pin = coordinate }
                }
            }
        }
    }
}
