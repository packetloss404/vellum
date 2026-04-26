import { FixtureHost } from "./FixtureHost";
import {
  stress2CaseFile,
  STRESS2_CHANGE_LOG,
  STRESS2_INVESTIGATION_LOG_COUNTS,
} from "../mocks/stress2CaseFile";

/**
 * Stress2Page — /stress2. Thin wrapper over FixtureHost mounted against
 * the fertility-decision-at-35 fixture. See FixtureHost for the shared
 * mechanics.
 */
export default function Stress2Page() {
  return (
    <FixtureHost
      dossier={stress2CaseFile}
      changeLog={STRESS2_CHANGE_LOG}
      investigationLogCounts={STRESS2_INVESTIGATION_LOG_COUNTS}
    />
  );
}
