import { FixtureHost } from "./FixtureHost";
import {
  stress4CaseFile,
  STRESS4_CHANGE_LOG,
  STRESS4_INVESTIGATION_LOG_COUNTS,
} from "../mocks/stress4CaseFile";

/**
 * Stress4Page — /stress4. Thin wrapper over FixtureHost mounted against
 * the pharmacy-tech-to-healthcare-data-analytics career-pivot fixture.
 * See FixtureHost for the shared mechanics.
 */
export default function Stress4Page() {
  return (
    <FixtureHost
      dossier={stress4CaseFile}
      changeLog={STRESS4_CHANGE_LOG}
      investigationLogCounts={STRESS4_INVESTIGATION_LOG_COUNTS}
    />
  );
}
