import { BrainCircuit, Play } from "lucide-react";
import { toast } from "sonner";
import { Stagger, StaggerItem } from "@/components/motion";
import { pct } from "@/components/metrics/fmt";
import { ErrorState, NotAvailable, Section, SectionSkeleton } from "@/components/metrics/section";
import { Button } from "@/components/ui/button";
import { errorMessage } from "@/lib/api";
import { useTrainModel } from "@/lib/feature-api/ml";
import type { ModelCard as ModelCardData, ModelKey } from "@/lib/feature-types";
import { ModelCard } from "./model-card";

const ORDER: ModelKey[] = ["router", "categoriser", "sentiment"];
const NAMES: Record<ModelKey, string> = { router: "intent router", categoriser: "transaction categoriser", sentiment: "sentiment model" };

function TrainButtons() {
  const train = useTrainModel();
  const start = (key: ModelKey) => {
    const id = toast.loading(`Training the ${NAMES[key]}…`);
    train.mutate(key, {
      onSuccess: (c) => toast.success(`${c.name} trained`, { id, description: `Accuracy ${pct(c.metrics.accuracy)}` }),
      onError: (e) => toast.error(errorMessage(e, "Training failed"), { id, description: undefined }),
    });
  };
  return (
    <div className="flex flex-wrap justify-center gap-2">
      {ORDER.map((key) => (
        <Button key={key} variant="outline" size="sm" onClick={() => start(key)} disabled={train.isPending}>
          <Play /> Train {NAMES[key]}
        </Button>
      ))}
    </div>
  );
}

interface ClassifiersSectionProps {
  models: ModelCardData[] | undefined;
  loading: boolean;
  error: unknown;
  onRetry: () => void;
  isAdmin: boolean;
}

/** 01 · The three trained classifiers (router, categoriser, sentiment), one card each. */
export function ClassifiersSection({ models, loading, error, onRetry, isAdmin }: ClassifiersSectionProps) {
  const sorted = [...(models ?? [])].sort((a, b) => ORDER.indexOf(a.key) - ORDER.indexOf(b.key));
  return (
    <Section
      id="classifiers"
      icon={BrainCircuit}
      eyebrow="01 · Classifiers"
      title="Trained classifiers"
      description="Three small supervised models trained for Sphura. Every number comes from the saved evaluation artifact: accuracy, macro-F1, per-class scores and the confusion matrix on a held-out test set."
    >
      {loading ? (
        <SectionSkeleton />
      ) : error ? (
        <ErrorState error={error} onRetry={onRetry} />
      ) : sorted.length === 0 ? (
        <NotAvailable
          title="No trained classifiers yet"
          description="Train the intent router, the transaction categoriser and the sentiment model from the training/ folder (see training/README.md). Their cards appear here as soon as backend/ml/artifacts holds a report."
          action={isAdmin ? <TrainButtons /> : undefined}
        />
      ) : (
        <Stagger className="space-y-4">
          {sorted.map((card) => (
            <StaggerItem key={card.key}>
              <ModelCard card={card} isAdmin={isAdmin} />
            </StaggerItem>
          ))}
        </Stagger>
      )}
    </Section>
  );
}
