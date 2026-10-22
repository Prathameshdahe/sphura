import { useState } from "react";
import { LoaderCircle, Plus } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAddMemory } from "@/lib/feature-api/memory";

const MAX = 500;

/** Add a fact manually ("I prefer metric units", "I'm studying for GATE"). */
export function AddMemoryForm({ disabled }: { disabled?: boolean }) {
  const [value, setValue] = useState("");
  const add = useAddMemory();
  const text = value.trim();

  const submit = () => {
    if (!text || add.isPending) return;
    add.mutate(text, {
      onSuccess: () => {
        setValue("");
        toast.success("Sphura will remember that");
      },
    });
  };

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
      className="flex flex-col gap-2 sm:flex-row"
    >
      <label htmlFor="memory-new" className="sr-only">
        New memory
      </label>
      <Input
        id="memory-new"
        value={value}
        onChange={(e) => setValue(e.target.value.slice(0, MAX))}
        placeholder="e.g. I'm salaried, in the new tax regime, and I invest through monthly SIPs"
        maxLength={MAX}
        disabled={disabled}
        className="h-10 flex-1 bg-card"
      />
      <Button type="submit" size="lg" className="h-10" disabled={!text || add.isPending || disabled}>
        {add.isPending ? <LoaderCircle className="animate-spin" /> : <Plus />} Remember
      </Button>
    </form>
  );
}
