import { FixtureHost } from "./FixtureHost";
import {
  stressCaseFile,
  STRESS_CHANGE_LOG,
  STRESS_INVESTIGATION_LOG_COUNTS,
} from "../mocks/stressCaseFile";

/**
 * StressPage — /stress. Thin wrapper over FixtureHost mounted against
 * the credit-card-debt negotiation fixture (the worst-case rendering
 * walk-through). See FixtureHost for the shared mechanics.
 */
export default function StressPage() {
  return (
    <FixtureHost
      dossier={stressCaseFile}
      changeLog={STRESS_CHANGE_LOG}
      investigationLogCounts={STRESS_INVESTIGATION_LOG_COUNTS}
    />
  );
}
