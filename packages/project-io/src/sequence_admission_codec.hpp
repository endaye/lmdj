#pragma once

#include <string_view>
#include <nlohmann/json.hpp>
#include <lmdj/project_io/sequence_journal.hpp>

namespace lmdj::project_io::admission_codec {
// Streaming preflight bounds admission arrays/records before JSON DOM allocation.
void preflight(std::string_view bytes);
nlohmann::json encode(const domain::PadSlotId& value);
nlohmann::json encode(const domain::PatternEvent& value);
nlohmann::json encode(const SequenceAdmissionIdentity& value);
nlohmann::json encode(const SequenceAdmissionPreparation& value);
nlohmann::json encode(const SequenceAdmissionCandidate& value);
nlohmann::json encode(const SequencePublicationAuthority& value);
nlohmann::json encode(const SequenceAdmissionFence& value);
nlohmann::json encode(const SequenceAdmissionClosure& value);
nlohmann::json encode(const SequenceOwnedPress& value);
nlohmann::json encode(const SequenceAdmissionCheckpoint& value);
nlohmann::json encode(const SequenceCandidateReceipt& value);
nlohmann::json encode(const SequenceAdmissionTransfer& value);
nlohmann::json encode(const SequenceAdmissionTimingProfile& value);
nlohmann::json encode(const SequenceAdmissionState& value);

// Throws on malformed or conflicting transitions. Only mutates the caller's copy.
// False denotes an exact durable retry and must never append another record.
bool apply(ActiveSequenceJournal& journal, const nlohmann::json& record,
           std::size_t* replay_candidate_bytes = nullptr);
SequenceAdmissionState snapshot(const nlohmann::json& encoded,
                                const ActiveSequenceJournal& journal);
bool blocks_flush(const ActiveSequenceJournal& journal);
bool blocks_switch(const ActiveSequenceJournal& journal,
                   const foundation::PatternId& target);
// Called on the replay copy only after the ordinary switch grammar is validated.
void reconcile_switch(ActiveSequenceJournal& journal);
}  // namespace lmdj::project_io::admission_codec
