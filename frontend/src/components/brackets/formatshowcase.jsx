import React from "react";
import { ArrowRight } from "lucide-react";
import MatchChip from "./matchchip";

// Illustrative previews for each tournament format shown on the /brackets page.
// All team names/scores below are sample data for visualization only.

function Column({ label, matches }) {
  return (
    <div className="flex flex-col gap-3 min-w-[180px]">
      <div className="text-[11px] font-heading font-bold uppercase tracking-wider text-center text-muted-foreground">
        {label}
      </div>
      <div className="flex flex-col gap-3 justify-around flex-1">
        {matches.map((m, i) => (
          <MatchChip key={i} a={m[0]} b={m[1]} />
        ))}
      </div>
    </div>
  );
}

// A labeled row of columns. A BracketPanel can hold several of these (e.g.
// "Winners Bracket" and "Losers Bracket") so multi-stage formats still render
// as one unified card instead of being split across separate panels.
function BracketGroup({ label, children }) {
  return (
    <div>
      {label && (
        <div className="text-[11px] font-heading font-bold uppercase tracking-wider mb-4 text-muted-foreground">
          {label}
        </div>
      )}
      <div className="flex gap-6">{children}</div>
    </div>
  );
}

function BracketPanel({ children }) {
  return (
    <div className="rounded-2xl border overflow-x-auto p-5 sm:p-6 glass border-border/60 space-y-8">
      {children}
    </div>
  );
}

// Text sits above the bracket, which then has the full section width to
// itself — a many-column bracket (round robin, swiss, group stage, ...)
// never has to fight the text for horizontal room, so nothing gets clipped
// at any viewport size.
function Section({ title, desc, buttonLabel, onClick, children }) {
  return (
    <div className="py-12 border-b border-border/40 last:border-0">
      <h3 className="font-display font-extrabold text-3xl mb-4">{title}</h3>
      <p className="text-muted-foreground leading-relaxed mb-6 max-w-2xl">{desc}</p>
      <button
        type="button"
        onClick={onClick}
        className="inline-flex items-center gap-2 px-5 py-3 rounded-xl font-heading font-bold text-sm transition-shadow mb-6 bg-primary text-primary-foreground hover:shadow-[0_0_28px_hsl(186_100%_50%/0.5)]"
      >
        {buttonLabel}
        <ArrowRight className="w-4 h-4" />
      </button>
      <div>{children}</div>
    </div>
  );
}

export default function FormatShowcase({ onSelect }) {
  return (
    <div className="mt-4">
      <Section
        title="Single Elimination Tournaments"
        desc="In this type of tournament, participants play one game each, and if they lose, they leave the tournament. Fast and decisive."
        buttonLabel="Create Single Elimination Tournament"
        onClick={() => onSelect("single")}
      >
        <BracketPanel>
          <BracketGroup>
            <Column label="R16" matches={[
              [{ team: "Lions", score: 3 }, { team: "Bulls", score: 1 }],
              [{ team: "Bears", score: 2 }, { team: "Hawks", score: 0 }],
              [{ team: "Wolves", score: 3 }, { team: "Owls", score: 1 }],
              [{ team: "Foxes", score: 2 }, { team: "Rams", score: 0 }],
              [{ team: "Eagles", score: 3 }, { team: "Cubs", score: 2 }],
              [{ team: "Sharks", score: 2 }, { team: "Pumas", score: 1 }],
              [{ team: "Tigers", score: 3 }, { team: "Vipers", score: 0 }],
              [{ team: "Knights", score: 2 }, { team: "Stags", score: 1 }],
            ]} />
            <Column label="QF" matches={[
              [{ team: "Lions", score: 3 }, { team: "Bears", score: 2 }],
              [{ team: "Wolves", score: 2 }, { team: "Foxes", score: 3 }],
              [{ team: "Eagles", score: 3 }, { team: "Sharks", score: 1 }],
              [{ team: "Tigers", score: 3 }, { team: "Knights", score: 2 }],
            ]} />
            <Column label="SF" matches={[
              [{ team: "Lions", score: 3 }, { team: "Foxes", score: 1 }],
              [{ team: "Eagles", score: 2 }, { team: "Tigers", score: 3 }],
            ]} />
            <Column label="Final" matches={[
              [{ team: "Lions", score: 3 }, { team: "Tigers", score: 2 }],
            ]} />
          </BracketGroup>
        </BracketPanel>
      </Section>

      <Section
        title="Double Elimination Tournaments"
        desc="Every player gets a second chance. Losers drop into a separate bracket and the winners of both brackets meet in a grand final. Works with any number of players, 4 and up."
        buttonLabel="Create Double Elimination Bracket"
        onClick={() => onSelect("double")}
      >
        <BracketPanel>
          <BracketGroup label="Winners Bracket">
            <Column label="QF" matches={[
              [{ team: "Lions", score: 3 }, { team: "Bulls", score: 1 }],
              [{ team: "Bears", score: 2 }, { team: "Hawks", score: 0 }],
              [{ team: "Wolves", score: 3 }, { team: "Owls", score: 1 }],
              [{ team: "Foxes", score: 2 }, { team: "Rams", score: 0 }],
            ]} />
            <Column label="SF" matches={[
              [{ team: "Lions", score: 3 }, { team: "Bears", score: 2 }],
              [{ team: "Wolves", score: 2 }, { team: "Foxes", score: 3 }],
            ]} />
            <Column label="WB Final" matches={[
              [{ team: "Lions", score: 3 }, { team: "Foxes", score: 1 }],
            ]} />
          </BracketGroup>
          <BracketGroup label="Losers Bracket → Grand Final">
            <Column label="LB R1" matches={[
              [{ team: "Bulls", score: 2 }, { team: "Hawks", score: 3 }],
              [{ team: "Owls", score: 3 }, { team: "Rams", score: 1 }],
            ]} />
            <Column label="LB R2" matches={[
              [{ team: "Hawks", score: 3 }, { team: "Bears", score: 2 }],
              [{ team: "Owls", score: 3 }, { team: "Wolves", score: 2 }],
            ]} />
            <Column label="LB Final" matches={[
              [{ team: "Foxes", score: 3 }, { team: "Hawks", score: 2 }],
            ]} />
            <Column label="Grand Final" matches={[
              [{ team: "Lions", score: 3 }, { team: "Foxes", score: 1 }],
            ]} />
          </BracketGroup>
        </BracketPanel>
      </Section>

      <Section
        title="3-Game Guarantee Tournaments"
        desc="Built on double elimination but tuned for events where every entry deserves real play time. Players who lose twice early drop into a guarantee bracket for a final match, so nobody leaves after just one or two games. Works with any number of players, 8 and up."
        buttonLabel="Create 3-Game Guarantee Bracket"
        onClick={() => onSelect("guarantee3")}
      >
        <BracketPanel>
          <BracketGroup label="Winners + Losers">
            <Column label="WB R1" matches={[
              [{ team: "Lions", score: 3 }, { team: "Bulls", score: 1 }],
              [{ team: "Bears", score: 2 }, { team: "Hawks", score: 0 }],
              [{ team: "Wolves", score: 3 }, { team: "Owls", score: 1 }],
              [{ team: "Foxes", score: 2 }, { team: "Rams", score: 0 }],
            ]} />
            <Column label="WB SF" matches={[
              [{ team: "Lions", score: 3 }, { team: "Bears", score: 2 }],
              [{ team: "Wolves", score: 2 }, { team: "Foxes", score: 3 }],
            ]} />
            <Column label="LB R1" matches={[
              [{ team: "Bulls", score: 2 }, { team: "Hawks", score: 3 }],
              [{ team: "Owls", score: 3 }, { team: "Rams", score: 1 }],
            ]} />
          </BracketGroup>
          <BracketGroup label="Guarantee Bracket + Grand Final">
            <Column label="Guarantee" matches={[
              [{ team: "Bulls", score: 2 }, { team: "Rams", score: 3 }],
            ]} />
            <Column label="LB Final" matches={[
              [{ team: "Foxes", score: 3 }, { team: "Hawks", score: 2 }],
            ]} />
            <Column label="Grand Final" matches={[
              [{ team: "Lions", score: 3 }, { team: "Foxes", score: 1 }],
            ]} />
          </BracketGroup>
        </BracketPanel>
      </Section>

      <Section
        title="Round Robin Tournaments"
        desc="In round robin tournaments, every participant plays against every other once. Works well for small and medium fields where you want fair, full coverage of pairings."
        buttonLabel="Generate Round Robin Bracket"
        onClick={() => onSelect("roundrobin")}
      >
        <BracketPanel>
          <BracketGroup>
            <Column label="Round 1" matches={[
              [{ team: "Lions", score: 3 }, { team: "Bears", score: 1 }],
              [{ team: "Wolves", score: 2 }, { team: "Foxes", score: 0 }],
              [{ team: "Eagles", score: 3 }, { team: "Tigers", score: 2 }],
            ]} />
            <Column label="Round 2" matches={[
              [{ team: "Lions", score: 2 }, { team: "Wolves", score: 1 }],
              [{ team: "Bears", score: 3 }, { team: "Eagles", score: 2 }],
              [{ team: "Foxes", score: 1 }, { team: "Tigers", score: 3 }],
            ]} />
            <Column label="Round 3" matches={[
              [{ team: "Lions", score: 3 }, { team: "Foxes", score: 0 }],
              [{ team: "Wolves", score: 2 }, { team: "Tigers", score: 3 }],
              [{ team: "Bears", score: 2 }, { team: "Eagles", score: 1 }],
            ]} />
            <Column label="Round 4" matches={[
              [{ team: "Lions", score: 3 }, { team: "Tigers", score: 2 }],
              [{ team: "Eagles", score: 1 }, { team: "Wolves", score: 3 }],
              [{ team: "Bears", score: 2 }, { team: "Foxes", score: 3 }],
            ]} />
          </BracketGroup>
        </BracketPanel>
      </Section>

      <Section
        title="Swiss System Tournaments"
        desc="Similar to round robin, but players don't face everyone. Instead, competitors with the same record are paired each round. Strong players meet strong, weaker meet weaker, and standings stay balanced without elimination."
        buttonLabel="Create Swiss System Bracket"
        onClick={() => onSelect("swiss")}
      >
        <BracketPanel>
          <BracketGroup>
            <Column label="Round 1" matches={[
              [{ team: "Lions", score: 3 }, { team: "Bulls", score: 1 }],
              [{ team: "Bears", score: 2 }, { team: "Hawks", score: 3 }],
              [{ team: "Wolves", score: 3 }, { team: "Owls", score: 1 }],
              [{ team: "Foxes", score: 0 }, { team: "Rams", score: 3 }],
            ]} />
            <Column label="Round 2" matches={[
              [{ team: "Lions", score: 2 }, { team: "Hawks", score: 3 }],
              [{ team: "Wolves", score: 3 }, { team: "Rams", score: 1 }],
              [{ team: "Bears", score: 3 }, { team: "Owls", score: 2 }],
              [{ team: "Bulls", score: 3 }, { team: "Foxes", score: 2 }],
            ]} />
            <Column label="Round 3" matches={[
              [{ team: "Hawks", score: 3 }, { team: "Wolves", score: 2 }],
              [{ team: "Lions", score: 3 }, { team: "Bears", score: 1 }],
              [{ team: "Rams", score: 2 }, { team: "Bulls", score: 3 }],
              [{ team: "Owls", score: 3 }, { team: "Foxes", score: 1 }],
            ]} />
          </BracketGroup>
        </BracketPanel>
      </Section>

      <Section
        title="Group Stage + Playoff"
        desc="Run round-robin groups first, then feed the top finishers into a knockout playoff. Optimal for larger fields where you want both fair early rounds and a decisive finish."
        buttonLabel="Create Group + Playoff Bracket"
        onClick={() => onSelect("group")}
      >
        <BracketPanel>
          <BracketGroup label="Group Stage">
            <Column label="Group A" matches={[
              [{ team: "Lions", score: 3 }, { team: "Bears", score: 1 }],
              [{ team: "Lions", score: 2 }, { team: "Wolves", score: 0 }],
              [{ team: "Bears", score: 3 }, { team: "Wolves", score: 2 }],
            ]} />
            <Column label="Group B" matches={[
              [{ team: "Eagles", score: 3 }, { team: "Foxes", score: 1 }],
              [{ team: "Eagles", score: 2 }, { team: "Tigers", score: 1 }],
              [{ team: "Foxes", score: 2 }, { team: "Tigers", score: 3 }],
            ]} />
            <Column label="Group C" matches={[
              [{ team: "Hawks", score: 3 }, { team: "Sharks", score: 2 }],
              [{ team: "Hawks", score: 3 }, { team: "Owls", score: 1 }],
              [{ team: "Sharks", score: 2 }, { team: "Owls", score: 0 }],
            ]} />
            <Column label="Group D" matches={[
              [{ team: "Bulls", score: 2 }, { team: "Rams", score: 1 }],
              [{ team: "Bulls", score: 3 }, { team: "Cubs", score: 0 }],
              [{ team: "Rams", score: 1 }, { team: "Cubs", score: 2 }],
            ]} />
          </BracketGroup>
          <BracketGroup label="Playoff">
            <Column label="SF" matches={[
              [{ team: "Lions", score: 3 }, { team: "Tigers", score: 1 }],
              [{ team: "Eagles", score: 2 }, { team: "Hawks", score: 3 }],
            ]} />
            <Column label="Final" matches={[
              [{ team: "Lions", score: 3 }, { team: "Hawks", score: 2 }],
            ]} />
          </BracketGroup>
        </BracketPanel>
      </Section>
    </div>
  );
}
