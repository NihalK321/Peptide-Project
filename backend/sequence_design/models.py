"""Explicit sequence choices and research goals; positions are one-based."""

from typing import ClassVar
from pydantic import Field, field_validator, model_validator
from ..schema import Model, STANDARD_AMINO_ACIDS


def amino_acids(values):
    if len(values) != len(set(values)) or any(value not in STANDARD_AMINO_ACIDS or len(value) != 1 for value in values):
        raise ValueError("Use unique uppercase standard one-letter amino-acid codes.")
    return values


class PositionChoices(Model):
    position: int = Field(ge=1, le=50, strict=True)
    choices: list[str] = Field(min_length=1, max_length=2)
    _choices = field_validator("choices")(amino_acids)


class DesignGoals(Model):
    ph: float = Field(default=7.4, ge=2, le=12)
    target_charge: float = Field(default=2, ge=-51, le=51)
    charge_weight: float = Field(default=1, ge=0, le=10)
    hydropathy_min: float = Field(default=-1.5, ge=-4.5, le=4.5)
    hydropathy_max: float = Field(default=0.5, ge=-4.5, le=4.5)
    hydropathy_weight: float = Field(default=0.5, ge=0, le=10)
    adjacent_repeat_weight: float = Field(default=0, ge=0, le=10)

    @model_validator(mode="after")
    def consistent(self):
        if self.hydropathy_min > self.hydropathy_max:
            raise ValueError("Hydropathy minimum cannot exceed maximum.")
        if self.charge_weight + self.hydropathy_weight + self.adjacent_repeat_weight <= 0:
            raise ValueError("At least one objective weight must be positive.")
        return self


class SequenceDesignRequest(Model):
    MAX_VARIABLE_POSITIONS: ClassVar[int] = 8
    MAX_CHOICES: ClassVar[int] = 2
    length: int = Field(default=8, ge=2, le=50, strict=True)
    template_sequence: str | None = None
    allowed_amino_acids: list[str] = Field(default_factory=lambda: list(STANDARD_AMINO_ACIDS), min_length=1, max_length=20)
    excluded_amino_acids: list[str] = Field(default_factory=list, max_length=20)
    required_amino_acids: list[str] = Field(default_factory=list, max_length=20)
    positions: list[PositionChoices] = Field(default_factory=list, max_length=50)
    max_mutations: int | None = Field(default=None, ge=0, le=50, strict=True)
    goals: DesignGoals = Field(default_factory=DesignGoals)
    layers: int = Field(default=1, ge=1, le=2, strict=True)
    max_iterations: int = Field(default=60, ge=10, le=120, strict=True)
    shots: int = Field(default=2048, ge=128, le=8192, strict=True)
    seed: int = Field(default=42, ge=0, le=2147483647, strict=True)
    _residues = field_validator("allowed_amino_acids", "excluded_amino_acids", "required_amino_acids")(amino_acids)

    @model_validator(mode="after")
    def consistent(self):
        if self.template_sequence is not None:
            if len(self.template_sequence) != self.length or any(letter not in STANDARD_AMINO_ACIDS for letter in self.template_sequence):
                raise ValueError("Template must match length and contain only uppercase standard residues.")
        elif self.max_mutations is not None:
            raise ValueError("A mutation budget requires a template sequence.")
        if self.max_mutations is not None and self.max_mutations > self.length:
            raise ValueError("Mutation budget cannot exceed peptide length.")
        effective = set(self.allowed_amino_acids) - set(self.excluded_amino_acids)
        if not effective or not set(self.required_amino_acids) <= effective:
            raise ValueError("Every required residue must be allowed and not excluded.")
        if len(self.required_amino_acids) > self.length:
            raise ValueError("More distinct required amino acids than available positions.")
        if len({rule.position for rule in self.positions}) != len(self.positions):
            raise ValueError("Position rules must be unique.")
        self.domains()  # Validate the exact space before chemistry or circuit work.
        return self

    def domains(self):
        effective = set(self.allowed_amino_acids) - set(self.excluded_amino_acids)
        rules = {rule.position: rule.choices for rule in self.positions}
        if any(position > self.length for position in rules):
            raise ValueError("A position rule lies outside the requested sequence length.")
        domains = []
        for index in range(self.length):
            choices = rules.get(index + 1)
            if choices is None:
                choices = [self.template_sequence[index]] if self.template_sequence is not None else sorted(effective)
            if not 1 <= len(choices) <= self.MAX_CHOICES:
                raise ValueError(f"Specify one fixed residue or up to {self.MAX_CHOICES} allowed choices per position.")
            if not set(choices) <= effective:
                raise ValueError(f"Position {index + 1} contains an excluded or globally disallowed residue.")
            domains.append(list(choices))
        if sum(len(choices) > 1 for choices in domains) > self.MAX_VARIABLE_POSITIONS:
            raise ValueError(f"This execution mode supports at most {self.MAX_VARIABLE_POSITIONS} variable positions (not a QPU hardware limit).")
        possible = {letter for choices in domains for letter in choices}
        if not set(self.required_amino_acids) <= possible:
            raise ValueError("A required amino acid cannot appear in any allowed position.")
        return domains


class MultiPositionChoices(PositionChoices):
    choices: list[str] = Field(min_length=1, max_length=20)


class MultiChoiceRequest(SequenceDesignRequest):
    """Compact binary blocks: at most two editable sites, five bits per site."""
    MAX_VARIABLE_POSITIONS: ClassVar[int] = 2
    MAX_CHOICES: ClassVar[int] = 20
    positions: list[MultiPositionChoices] = Field(default_factory=list, max_length=50)


class LargeSequenceRequest(SequenceDesignRequest):
    MAX_VARIABLE_POSITIONS: ClassVar[int] = 50
    max_iterations: int = Field(default=10, ge=10, le=30, strict=True)
    mps_bond_dimension: int = Field(default=16, ge=2, le=32, strict=True)
    training_shots: int = Field(default=64, ge=64, le=256, strict=True)
    initial_gamma: float = Field(default=1, ge=-6.3, le=6.3)
    initial_beta: float = Field(default=.5, ge=-6.3, le=6.3)

    @model_validator(mode="after")
    def bounded_depth(self):
        if sum(len(row) == 2 for row in self.domains()) > 20 and self.layers > 1:
            raise ValueError("Large-circuit execution above 20 qubits is limited to one QAOA layer in this prototype.")
        return self


class StructureRequest(Model):
    sequence: str = Field(min_length=2, max_length=50)

    @field_validator("sequence")
    @classmethod
    def standard(cls, sequence):
        if any(letter not in STANDARD_AMINO_ACIDS for letter in sequence):
            raise ValueError("Use uppercase standard amino-acid letters.")
        return sequence
