from typing import List, Optional, Dict, NamedTuple
from copy import deepcopy

import numpy as np
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm, PowerNorm

from util.datasets import RespiratoryEventType, RespiratoryEvent
from .overlaps import get_overlaps


__author__ = "Robert Voelckner"
__copyright__ = "Copyright 2021"
__license__ = "MIT"


Scores = NamedTuple("Scores", precision=float, recall=float, f1_score=float)


class EventBasedConfusionMatrix:
    _class_labels = [k.name for k in RespiratoryEventType]

    def __init__(self, annotated_events: List[RespiratoryEvent], detected_events: List[RespiratoryEvent]):
        # Generate our confusion matrix
        data = np.zeros(shape=(len(RespiratoryEventType), len(RespiratoryEventType)), dtype=int)
        overlaps = get_overlaps(annotated_events=annotated_events, detected_events=detected_events)
        for o in overlaps:
            data[o.annotated.event_type.value, o.detected.event_type.value] += 1
        self._matrix = data  # FIRST DIM: true labels,  SECOND DIM: predicted labels

    @classmethod
    def empty(cls) -> "EventBasedConfusionMatrix":
        return cls(annotated_events=[], detected_events=[])

    def __add__(self, other: "EventBasedConfusionMatrix") -> "EventBasedConfusionMatrix":
        new = deepcopy(self)
        new._matrix += other._matrix
        return new

    def __getitem__(self, index):
        """
        Returns the confusion matrix elements.

        FIRST DIM: true labels,  SECOND DIM: predicted labels
        """
        return self._matrix[index]

    def plot(self, title: Optional[str] = "Confusion matrix for class confidence of detected events", power_norm_gamma=0.3):
        norm = PowerNorm(gamma=power_norm_gamma, vmin=self._matrix.min(initial=0), vmax=self._matrix.max(initial=1))
        ax = sns.heatmap(self._matrix, annot=True, fmt="d", norm=norm, xticklabels=self._class_labels,
                         yticklabels=self._class_labels, cmap=sns.color_palette("Blues"), cbar=False)
        ax.set_yticklabels(labels=ax.get_yticklabels(), va="center")
        # ax.yaxis.tick_right()
        plt.xlabel("Predicted labels", fontweight="bold")
        plt.ylabel("True labels", fontweight="bold")
        ax.xaxis.set_label_position("top")
        ax.yaxis.set_label_position("right")
        if title is not None:
            plt.title(title, pad=25, fontdict={'fontsize': 14, 'fontweight': 'medium'})
        plt.show()

    def get_class_based_scores(self) -> Dict[RespiratoryEventType, Scores]:
        class_based_scores: Dict[RespiratoryEventType, Scores] = {}
        for klass in RespiratoryEventType:
            index = klass.value
            with np.errstate(divide='ignore', invalid='ignore'):  # Helps to suppress divide-by-0-warnings
                p_ = self._matrix[index, index] / self._matrix[:, index].sum()  # can be NaN!
                r_ = self._matrix[index, index] / self._matrix[index, :].sum()  # can be NaN!
                p_ = np.nan_to_num(p_)
                r_ = np.nan_to_num(r_)
                f_ = (p_ * r_ * 2) / (p_ + r_)
                f_ = np.nan_to_num(f_)
            class_based_scores[klass] = Scores(precision=float(p_), recall=float(r_), f1_score=float(f_))
        return class_based_scores

    def get_macro_scores(self) -> Scores:
        class_based_scores = self.get_class_based_scores()

        macro_precision = np.mean([s.precision for s in class_based_scores.values()])
        macro_recall = np.mean([s.recall for s in class_based_scores.values()])
        macro_precision = np.nan_to_num(macro_precision)
        macro_recall = np.nan_to_num(macro_recall)

        with np.errstate(divide='ignore', invalid='ignore'):  # Helps to suppress divide-by-0-warnings
            macro_f1_score = (macro_precision * macro_recall * 2) / (macro_precision + macro_recall)
            macro_f1_score = np.nan_to_num(macro_f1_score)

        return Scores(precision=float(macro_precision), recall=float(macro_recall), f1_score=float(macro_f1_score))


def test_():
    annotated_events = [RespiratoryEvent(start=pd.to_timedelta("1 min"), aux_note=None, end=pd.to_timedelta("2 min"), event_type=RespiratoryEventType.Hypopnea),
                        RespiratoryEvent(start=pd.to_timedelta("3 min"), aux_note=None, end=pd.to_timedelta("4 min"), event_type=RespiratoryEventType.MixedApnea),
                        RespiratoryEvent(start=pd.to_timedelta("5 min"), aux_note=None, end=pd.to_timedelta("6 min"), event_type=RespiratoryEventType.ObstructiveApnea),
                        RespiratoryEvent(start=pd.to_timedelta("7 min"), aux_note=None, end=pd.to_timedelta("8 min"), event_type=RespiratoryEventType.Hypopnea)]
    detected_events = [RespiratoryEvent(start=pd.to_timedelta("1 min"), aux_note=None, end=pd.to_timedelta("2 min"), event_type=RespiratoryEventType.Hypopnea),
                       RespiratoryEvent(start=pd.to_timedelta("3 min"), aux_note=None, end=pd.to_timedelta("4 min"), event_type=RespiratoryEventType.MixedApnea),
                       RespiratoryEvent(start=pd.to_timedelta("5 min"), aux_note=None, end=pd.to_timedelta("6 min"), event_type=RespiratoryEventType.ObstructiveApnea),
                       RespiratoryEvent(start=pd.to_timedelta("7 min"), aux_note=None, end=pd.to_timedelta("8 min"), event_type=RespiratoryEventType.CentralApnea)]

    confusion_matrix = EventBasedConfusionMatrix(annotated_events=annotated_events, detected_events=detected_events)
    class_based_scores = confusion_matrix.get_class_based_scores()
    macro_scores = confusion_matrix.get_macro_scores()
    confusion_matrix.plot()