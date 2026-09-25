// Setting up your profile after the first sign-in: name, birthday (21+),
// neighborhood, location, interests.

import SwiftUI

struct OnboardingView: View {
    @Environment(AppModel.self) private var model

    @State private var firstName = ""
    @State private var birthday = Calendar.current.date(byAdding: .year, value: -25, to: .now)!
    @State private var neighborhood = ""
    @State private var interests: [String] = []
    @State private var working = false
    @State private var error: String?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                VStack(alignment: .leading, spacing: 6) {
                    ScreenTitle(text: "Who are you?")
                    Text("This is what people see when you show up in Discover.")
                        .foregroundStyle(Theme.textDim)
                }
                .padding(.top, 24)

                VStack(alignment: .leading, spacing: 12) {
                    SectionLabel("About you")
                    TextField("", text: $firstName, prompt: Text("First name").foregroundStyle(Theme.textDim))
                        .textContentType(.givenName)
                        .fieldStyle()
                    DatePicker("Birthday", selection: $birthday, displayedComponents: .date)
                        .fieldStyle()
                    TextField("", text: $neighborhood, prompt: Text("Neighborhood").foregroundStyle(Theme.textDim))
                        .fieldStyle()
                }

                VStack(alignment: .leading, spacing: 12) {
                    SectionLabel("Your interests")
                    Text("Be specific: \"Kid A era Radiohead\" beats \"music\". Up to 12.")
                        .font(.footnote)
                        .foregroundStyle(Theme.textDim)
                    InterestsEditor(interests: $interests)
                }
                .card()

                ErrorText(text: error)

                VStack(spacing: 10) {
                    Button("I'm ready", action: save)
                        .buttonStyle(.hot)
                        .disabled(working || firstName.isEmpty || interests.isEmpty)
                    Label(
                        "We'll ask for your location. Nobody sees where you are, only roughly how far.",
                        systemImage: "location.fill"
                    )
                    .font(.footnote)
                    .foregroundStyle(Theme.textDim)
                }
            }
            .padding(20)
        }
        .scrollDismissesKeyboard(.interactively)
        .partyScreen()
    }

    private func save() {
        working = true
        error = nil
        Task {
            defer { working = false }
            do {
                let spot = try await Location.current()
                let changes = ProfileUpdate(
                    firstName: firstName.trimmingCharacters(in: .whitespaces),
                    birthdate: birthday.birthdateString,
                    neighborhood: neighborhood.isEmpty ? nil : neighborhood,
                    latitude: spot.latitude,
                    longitude: spot.longitude,
                    downToParty: true
                )
                try await model.saveProfile(changes, interests: interests)
            } catch {
                self.error = error.localizedDescription
            }
        }
    }
}

/// Type an interest and pick from popular spellings as you go. Your
/// interests show as chips; tap the x to drop one.
struct InterestsEditor: View {
    @Environment(AppModel.self) private var model
    @Binding var interests: [String]
    /// 12 for a profile, 5 for a party.
    var limit = 12

    @State private var draft = ""
    @State private var suggestions: [InterestSuggestion] = []
    @FocusState private var typing: Bool

    private let maxLength = 40

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            if !interests.isEmpty {
                FlowLayout {
                    ForEach(interests, id: \.self) { interest in
                        InterestChip(text: interest) {
                            withAnimation(.snappy) { interests.removeAll { $0 == interest } }
                        }
                    }
                }
            }

            if interests.count < limit {
                HStack {
                    Image(systemName: "plus.circle.fill").foregroundStyle(Theme.hot)
                    TextField("", text: $draft, prompt: Text("Add an interest").foregroundStyle(Theme.textDim))
                        .focused($typing)
                        .onSubmit { add(draft) }
                        .submitLabel(.done)
                }
                .fieldStyle()
                // Tapping anywhere on the box, not just the text, starts typing.
                .contentShape(.rect)
                .onTapGesture { typing = true }
                .onChange(of: draft) { _, text in
                    if text.count > maxLength { draft = String(text.prefix(maxLength)) }
                }
                // Re-runs (and cancels the last run) every time the text changes.
                .task(id: draft) { await loadSuggestions(for: draft) }

                // Suggesting existing spellings is how wording converges, so
                // "radiohead" and "Radiohead!" end up as one interest.
                if !suggestions.isEmpty {
                    FlowLayout {
                        ForEach(suggestions, id: \.display) { suggestion in
                            Button { add(suggestion.display) } label: {
                                HStack(spacing: 6) {
                                    Text(suggestion.display)
                                    Text("\(suggestion.usageCount)")
                                        .font(.caption.weight(.heavy))
                                        .foregroundStyle(Theme.textDim)
                                }
                            }
                            .buttonStyle(.soft(Theme.color(for: suggestion.display)))
                        }
                    }
                }
            }
        }
    }

    private func add(_ text: String) {
        let clean = text.trimmingCharacters(in: .whitespaces)
        guard clean.count >= 2,
              !interests.contains(where: { $0.caseInsensitiveCompare(clean) == .orderedSame })
        else { return }
        withAnimation(.snappy) { interests.append(clean) }
        draft = ""
        suggestions = []
        typing = true  // keep the keyboard up for the next one
    }

    private func loadSuggestions(for text: String) async {
        guard text.count >= 2 else {
            suggestions = []
            return
        }
        try? await Task.sleep(for: .milliseconds(250))  // wait until they pause typing
        guard !Task.isCancelled else { return }
        let found = (try? await model.api.suggestInterests(text)) ?? []
        suggestions = found.filter { !interests.contains($0.display) }
    }
}
