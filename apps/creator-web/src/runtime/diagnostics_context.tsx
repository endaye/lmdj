import {createContext, useContext} from "react";

// Lets any Creator surface record a failure in Developer diagnostics without
// threading a callback through its parents (#1680). The Workspace provides
// its reportFailure; outside a Workspace, failures are not recorded.
export type ReportFailure = (operation: string, error: unknown) => string;

const NOT_RECORDED: ReportFailure = () => "INTERNAL_ERROR";

const DiagnosticsContext = createContext<ReportFailure>(NOT_RECORDED);

export const DiagnosticsProvider = DiagnosticsContext.Provider;

export function useReportFailure(): ReportFailure {
  return useContext(DiagnosticsContext);
}
