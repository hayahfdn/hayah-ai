// «حفظ في معرض الصور»: puts a finished image straight into the phone's photos.
// Phones get the share sheet with the image only ("Save Image" / "حفظ الصورة" puts it in Photos or the
// gallery); computers and browsers that cannot share files download the same PNG. Callers prepare the
// file in advance when they can, so the share opens straight from the tap.
export type PhotoResult = "shared" | "downloaded" | "cancelled" | "tap_again";

export function downloadBlob(b: Blob, name: string) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(b); a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 4000);
}

export async function saveToPhotos(file: File): Promise<PhotoResult> {
  const nav: any = navigator;
  const phone = /Android|iPhone|iPad|iPod|Mobile/i.test(navigator.userAgent) || (navigator.maxTouchPoints > 1 && /Mac/.test(navigator.platform));
  if (phone && nav.canShare && nav.canShare({ files: [file] })) {
    try { await nav.share({ files: [file] }); return "shared"; }
    catch (e: any) {
      if (e?.name === "AbortError") return "cancelled";
      if (e?.name === "NotAllowedError") return "tap_again";  // the tap expired while the file was being made
    }
  }
  downloadBlob(file, file.name);
  return "downloaded";
}
