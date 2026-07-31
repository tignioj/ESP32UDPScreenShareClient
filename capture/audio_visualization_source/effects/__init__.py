"""Explicit registry: add or remove one effect module in this list only."""

from .aurora import AuroraEffect
from .base import AudioEffect, ParameterSpec, metadata_for
from .chroma_ring import ChromaRingEffect
from .mirror_bars import MirrorBarsEffect
from .orbital_rings import OrbitalRingsEffect
from .particles import ParticlesEffect
from .pulse_tunnel import PulseTunnelEffect
from .spectrum_bars import SpectrumBarsEffect
from .starburst import StarburstEffect
from .waterfall import WaterfallEffect
from .waveform import WaveformEffect


EFFECT_TYPES = (
    WaveformEffect,
    SpectrumBarsEffect,
    OrbitalRingsEffect,
    ChromaRingEffect,
    PulseTunnelEffect,
    MirrorBarsEffect,
    AuroraEffect,
    StarburstEffect,
    WaterfallEffect,
    ParticlesEffect,
)


def create_effects() -> dict[str, AudioEffect]:
    return {effect_type.effect_id: effect_type() for effect_type in EFFECT_TYPES}


def get_effect_catalog():
    return metadata_for(EFFECT_TYPES)


__all__ = ["AudioEffect", "ParameterSpec", "create_effects", "get_effect_catalog"]
