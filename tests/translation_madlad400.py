"""Madlad400 EN->RO translation helper used by dataset generation providers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass
class Madlad400Config:
    """Runtime options for loading/generating with a Madlad model."""

    model_name: str = "google/madlad400-10b-mt"
    max_new_tokens: int = 512
    num_beams: int = 4
    device_map: str = "auto"


class Madlad400Translator:
    """Tiny wrapper around Hugging Face generation for translation."""

    def __init__(self, config: Madlad400Config | None = None) -> None:
        cfg = config or Madlad400Config()
        self.config = cfg
        try:
            from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
        except Exception as exc:
            raise RuntimeError(
                "Missing transformers dependency required for Madlad translation."
            ) from exc

        self._tokenizer = AutoTokenizer.from_pretrained(cfg.model_name)
        self._model = AutoModelForSeq2SeqLM.from_pretrained(
            cfg.model_name,
            device_map=cfg.device_map,
        )

    def translate(self, text: str, target_lang: str = "ro") -> str:
        """Translate text to target language with MADLAD language tag prefix."""
        source = str(text or "").strip()
        if not source:
            return ""

        prompt = f"<2{target_lang}> {source}"
        inputs = self._tokenizer(prompt, return_tensors="pt")
        if hasattr(self._model, "device"):
            model_device = self._model.device
            inputs = {k: v.to(model_device) for k, v in inputs.items()}

        try:
            import torch

            no_grad_ctx = torch.no_grad()
        except Exception:
            no_grad_ctx = None

        if no_grad_ctx is None:
            output_ids = self._model.generate(
                **inputs,
                max_new_tokens=self.config.max_new_tokens,
                num_beams=self.config.num_beams,
                do_sample=False,
            )
        else:
            with no_grad_ctx:
                output_ids = self._model.generate(
                    **inputs,
                    max_new_tokens=self.config.max_new_tokens,
                    num_beams=self.config.num_beams,
                    do_sample=False,
                )

        return self._tokenizer.decode(output_ids[0], skip_special_tokens=True).strip()

    def translate_en_to_ro(self, text: str) -> str:
        """Convenience shortcut for English->Romanian translation."""
        return self.translate(text=text, target_lang="ro")


def build_madlad_translator(config_overrides: Dict[str, object] | None = None) -> Madlad400Translator:
    """Construct translator from optional dictionary overrides."""
    cfg = Madlad400Config()
    if config_overrides:
        cfg.model_name = str(config_overrides.get("model_name", cfg.model_name))
        cfg.max_new_tokens = int(
            config_overrides.get("max_new_tokens", cfg.max_new_tokens)
        )
        cfg.num_beams = int(config_overrides.get("num_beams", cfg.num_beams))
        cfg.device_map = str(config_overrides.get("device_map", cfg.device_map))
    return Madlad400Translator(config=cfg)


if __name__ == "__main__":
    translator = Madlad400Translator()
    samples = [
        "Find me the trains that leave at 14:00 from Bucharest to Barlad but do not go through Ploiesti.",
        "Show all schools from Cluj county with more than 500 students.",
    ]
    for item in samples:
        print(translator.translate_en_to_ro(item))
