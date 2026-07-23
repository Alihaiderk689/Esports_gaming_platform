import React from "react";
import { FileText, FileX, ArrowLeft, ExternalLink } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";

export function DocBadge({ url, label, onPreview }) {
  if (!url) {
    return (
      <span className="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-full bg-muted text-muted-foreground">
        <FileX className="w-3 h-3" />
        {label}
      </span>
    );
  }
  return (
    <button
      onClick={(e) => {
        e.stopPropagation();
        onPreview(url, label);
      }}
      className="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-full bg-primary/10 text-primary hover:bg-primary/20 transition-colors"
    >
      <FileText className="w-3 h-3" />
      {label}
    </button>
  );
}

export function DocPreviewDialog({ doc, onClose }) {
  return (
    <Dialog open={!!doc} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-3xl max-h-[85vh] flex flex-col">
        <DialogHeader>
          <DialogTitle>{doc?.label}</DialogTitle>
        </DialogHeader>
        {doc && (
          <iframe title={doc.label} src={doc.url} className="w-full flex-1 min-h-[60vh] rounded-lg border border-border/60 bg-muted/20" />
        )}
        <div className="flex items-center justify-between gap-2 pt-1">
          <button
            onClick={onClose}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-heading font-semibold bg-muted hover:bg-muted/70 transition-colors"
          >
            <ArrowLeft className="w-4 h-4" /> Back
          </button>
          {doc && (
            <a
              href={doc.url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm text-muted-foreground hover:text-primary transition-colors"
            >
              <ExternalLink className="w-4 h-4" /> Open in new tab
            </a>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
