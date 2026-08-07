import {useReducer} from "react";

import {BankSelector} from "./components/bank_selector";
import {ErrorPanel} from "./components/error_panel";
import {ModeRail} from "./components/mode_rail";
import {PadSurface} from "./components/pad_surface";
import {ProjectSurface} from "./components/project_surface";
import {StatusBar} from "./components/status_bar";
import {
  creatorReducer,
  initialCreatorState,
  type CreatorState,
} from "./state/creator_state";

interface AppProps {
  initialState?: CreatorState;
}

export function App({initialState = initialCreatorState}: AppProps) {
  const [state, dispatch] = useReducer(creatorReducer, initialState);
  return (
    <div className="workspace">
      <StatusBar state={state} />
      <ModeRail />
      <ProjectSurface state={state} />
      <section className="pads" aria-label="Instrument">
        <BankSelector
          activeBank={state.activeBank}
          onSelect={(bank) => dispatch({type: "bank-selected", bank})}
        />
        <PadSurface state={state} />
      </section>
      <ErrorPanel code={state.runtime.errorCode} />
    </div>
  );
}
