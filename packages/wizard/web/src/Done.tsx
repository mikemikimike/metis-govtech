// The end of the interview, marked in the conversation. The two actions on a finished experiment —
// downloading it and running it — now live at the foot of the document pane, on the artifact they
// act on. So this panel no longer carries buttons: it is the moment of completion in the chat, and
// it points the user to the pane where the file is waiting.

import { PartyPopper } from "lucide-react";
import { Panel } from "./ui";

export function Done() {
  return (
    // Reaching the end is a state worth marking, but not with a coloured left-rule — that reads
    // as generated chrome and breaks the borders-not-accents rule. The panel stays a plain
    // bordered card; the accent lands only on the heading and its icon, where "ready" is the state
    // being signalled.
    <Panel className="flex flex-col gap-2 p-5">
      <h2 className="flex items-center gap-2 text-base font-semibold text-accent">
        <PartyPopper size={18} strokeWidth={1.75} aria-hidden />
        Your evaluation is ready
      </h2>
      <p className="text-sm text-muted-foreground">
        Download it, or run the evaluation, from the foot of the product profile.
      </p>
    </Panel>
  );
}
