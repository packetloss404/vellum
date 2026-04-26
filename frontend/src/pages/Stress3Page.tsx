import { FixtureHost } from "./FixtureHost";
import {
  stress3CaseFile,
  STRESS3_CHANGE_LOG,
  STRESS3_INVESTIGATION_LOG_COUNTS,
} from "../mocks/stress3CaseFile";

/**
 * Stress3Page — /stress3. Thin wrapper over FixtureHost mounted against
 * the move-closer-to-mom fixture (20-month-old, mortgage-rate lock-in,
 * aging-parent decline-timing unknown). See FixtureHost for the shared
 * mechanics.
 */
export default function Stress3Page() {
  return (
    <FixtureHost
      dossier={stress3CaseFile}
      changeLog={STRESS3_CHANGE_LOG}
      investigationLogCounts={STRESS3_INVESTIGATION_LOG_COUNTS}
    />
  );
}
