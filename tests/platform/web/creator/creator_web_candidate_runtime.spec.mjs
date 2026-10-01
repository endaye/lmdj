import {registerCandidateJourneys} from "../candidate_journey.mjs";
import {wakeAudioWithPad} from "./fixtures/creator_audio.mjs";
registerCandidateJourneys("Creator Web", {wakeCreatorAudio: wakeAudioWithPad});
