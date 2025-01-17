"""
Implementation from https://github.com/bigscience-workshop/lm-evaluation-harness/blob/master/lm_eval/tasks/gem_wikilingua.py
---

WikiLingua: A New Benchmark Dataset for Cross-Lingual Abstractive Summarization
https://arxiv.org/pdf/2010.03093.pdf

Wikilingua is a large-scale (~770k article-summary pairs), multilingual dataset for the evaluation of cross-lingual abstractive systems.
It consists of parallel articles and summaries (article-summary pairs) from WikiHow across 18 languages (i.e. all the languages available on WikiHow).
It contains 141,457 unique English articles and each of the other 17 languages has on average, 42,783 articles that align with an article in English.
This dataset is part of the GEM Benchmark. (Description from https://gem-benchmark.com/data_cards/WikiLingua)


Homepage: None, Repo: https://github.com/esdurmus/Wikilingua
"""
import random
import typing
from lm_eval.base import Task, rf
from lm_eval.metrics import mean
from lm_eval import utils
from typing import Callable, List, Mapping, Optional, Tuple, Union
import datasets
import numpy as np
from lm_eval.tasks.dataset_paths import dataset_paths


_CITATION = """
@inproceedings{ladhak-wiki-2020,
    title={WikiLingua: A New Benchmark Dataset for Multilingual Abstractive Summarization},
    author={Faisal Ladhak, Esin Durmus, Claire Cardie and Kathleen McKeown},
    booktitle={Findings of EMNLP, 2020},
    year={2020}
}"""

class PromptSourceTask(Task):
    """These are the metrics from promptsource that we have
    added default behavior for. If you want to add default behavior for a new metric,
    update the functions below. If you want to use one of the following metrics,
    *and* add additional custom processing, override `process_results`, `higher_is_better`, and `aggregation`.
    """

    CONFIGURED_RANKED_CHOICE_PS_METRICS = {"Accuracy"}
    CONFIGURED_GENERATION_PS_METRICS = {"BLEU", "ROUGE", "SARI"}
    SPLIT = None

    def __init__(
        self,
        data_dir: Optional[str] = None,
        cache_dir: Optional[str] = None,
        download_mode: Optional[str] = None,
        prompt_template: str = None,
        example_separator: Optional[str] = "\n###\n",
        text_target_separator: Optional[str] = " ",
        save_examples: Optional[bool] = True,
    ):
        """
        Args:
            save_examples (bool, optional, defaults to True):
                Whether to save each example and corresponding model predictions
                to an output `dict`.

            > Few-shot prompting args

            example_separator (str, optional, defaults to '\n###\n'):
                The string that will be used to separate the few-shot examples
                from the prompt example.
                Default: '\n###\n'
                    See Webson & Pavlick (2022) https://arxiv.org/pdf/2109.01247.pdf
                    for justification of this separator.
            text_target_separator (str, optional, defaults to ' '):
                The string that will be used to separate the prompt example
                from the target text.
                NOTE: This is assumed to be some form of whitespace-only separation,
                    e.g. "\n\n", "\t", "  ", etc. Otherwise, you should update
                    the Task's `promptsource` template with the appropriate
                    separator(s).
                Example:
                    Q: Where is the Eiffel Tower located? A:{text_target_separator}Paris
        """
        self.DATASET_NAME = self.LANG_DATASET
        assert isinstance(save_examples, bool), "`save_examples` must be a bool."
        assert isinstance(example_separator, str) and isinstance(
            text_target_separator, str
        ), "Separator args must be strings."
        assert (
            text_target_separator.isspace()
        ), f"`text_target_separator` must be whitespace only. Got: `{text_target_separator}`"


        super().__init__(data_dir, cache_dir, download_mode)
        self.prompt_template = prompt_template
        self.save_examples = save_examples
        self.example_separator = example_separator
        self.text_target_separator = text_target_separator

    def stop_sequences(self) -> List[str]:
        """Denote where the generation should end based on the few-shot example
        separator.

        NOTE: Override this if you want to use a sequence other than just the
        task's few-shot example separator.
        """
        return [self.example_separator]

    def max_generation_length(self) -> Optional[int]:
        """Denote where the max length of the generation if it is obvious from the task."""
        return None

    def evaluation_docs(self) -> datasets.Dataset:
        """Returns the `dataset` split to be used for evaluation."""
        if self.has_test_docs():
            return self.test_docs()
        elif self.has_validation_docs():
            return self.validation_docs()
        else:
            raise RuntimeError("Task has neither test_docs nor validation_docs")

    def fewshot_docs(self) -> datasets.Dataset:
        """Returns the `dataset` split that the few-shot examples should be sample
        from. This prioritizes the `train_docs` split as the few-shot example
        source, then `validation_docs`, and lastly `test_docs`.
        """
        if self.has_training_docs():
            return self.training_docs()
        elif self.has_validation_docs():
            return self.validation_docs()
        else:
            return self.test_docs()

    def doc_to_text(self, doc: dict) -> str:
        breakpoint()
        text, _ = self.prompt_template.apply(doc)
        return text

    def doc_to_target(self, doc: dict) -> List[str]:
        _, target = self.prompt_template.apply(doc)
        return target

    def doc_to_rawtext(self, doc: dict) -> str:
        """This should be used for selecting the raw text of the document.

        The current use case is for computing SARI which requires the text
        without the prompt. The `text` field is not standardized across tasks
        so this is task specific.
        """
        raise NotImplementedError("This is task specific.")

    def invalid_doc_for_prompt(self, doc) -> bool:
        """Some prompts may not work for some documents.
        Default: False
        """
        return False

    def format_example(self, text: str, target: str, separator: str) -> str:
        """Returns the text and target combined by the specified `separator`"""
        return text + separator + target

    def fewshot_examples(
        self,
        docs: datasets.Dataset,
        k: int,
        rnd: np.random.Generator,
        prompt: dict = None,
    ) -> Tuple[List[dict], List[int]]:
        """Returns `k` random examples from the set of documents in `docs`.

        Args:
            docs (datasets.Dataset):
                The dataset of documents to sample few-shot examples from.
            k (int):
                The number of few-shot examples.
            rnd (np.random.Generator):
                The pseudo-random number generator used to randomly sample examples.
            prompt (Optional[dict]):
                The prompt document. Specify this to ensure the prompt is not in
                the set of few-shot examples.

        Returns:
            A tuple of two lists. The first list contains the few-shot examples
        """
        def random_indices():
            while True:
                #breakpoint()
                yield from random.sample(range(len(docs)), 10 * k)
                # yield from np.random.Generator.choice(
                #     np.arange(len(docs)), size=(10 * k,), replace=False, shuffle=True
                # ).tolist()
        i = 0
        fewshot_examples, fewshot_idx = [], []
        for idx in random_indices():
            if i >= k:  # Break when we have enough examples.
                break
            is_same_prompt = prompt is not None and all(
                # Skips the `doc_id` key assigned to `prompt`s during eval pre-processing.
                docs[idx][k] == prompt[k]
                for k in docs[idx].keys()
            )
            if self.invalid_doc_for_prompt(docs[idx]) or is_same_prompt:
                continue
            fewshot_examples.append(docs[idx])
            fewshot_idx.append(int(idx))
            i += 1
        return fewshot_examples, fewshot_idx

    def fewshot_context(
        self, doc: dict, num_fewshot: int, rnd: Optional[np.random.Generator], description:str
    ) -> Tuple[str, dict]:
        """Returns a few-shot context string made up of `num_fewshot` number of
        labeled examples, and an appended prompt example without labeling.

        Args:
            doc (dict):
                The document as returned from training_docs, validation_docs, or test_docs.
            num_fewshot (int):
                The number of fewshot examples to provide in the returned context string.
            rnd (numpy.random.Generator):
                The pseudo-random number generator used to randomly sample few-shot examples.

        Returns:
            A few-shot context string and a dictionary containing few-shot context
            logging information.
                ctx (str):
                    The fewshot context.
                logging_info (dict):
                    A `dict` of logging info that can be used to identify few-shot
                    sources.
        """
        self.num_fewshot = num_fewshot
        assert (
            rnd is not None
        ), "A `numpy.random.Generator` argument must be provided to `rnd`"

        if num_fewshot == 0:
            labeled_examples = ""
            fewshot_idx, fewshot_target_idx, fewshot_src = ([], [], None)
        else:
            # Construct few-shot labeled examples.
            fewshot_docs = self.fewshot_docs()
            fewshot_src = str(fewshot_docs.split)
            fewshot_examples, fewshot_idx = self.fewshot_examples(
                fewshot_docs, k=num_fewshot, rnd=rnd, prompt=doc
            )
            labeled_examples_list = []
            fewshot_target_idx = []
            for fewshot_example in fewshot_examples:
                text = self.doc_to_text(fewshot_example)
                targets = self.doc_to_target(fewshot_example)
                # Choose 1 random target from multi-reference targets.
                if isinstance(targets, list):
                    target_idx = random.randint(0,len(targets))#int(rnd.integers(0, len(targets)))
                    breakpoint()
                    target = targets[target_idx].strip()
                    fewshot_target_idx.append(target_idx)
                else:
                    target = targets

                labeled_examples_list.append(
                    self.format_example(text, target, self.text_target_separator)
                )

            labeled_examples = self.example_separator.join(labeled_examples_list)
            # Leave an extra `example_separator` right before the prompt.
            labeled_examples += self.example_separator

        prompt = self.doc_to_text(doc)
        ctx = labeled_examples + prompt
        logging_info = {
            "fewshot_idx": fewshot_idx,
            "fewshot_target_idx": fewshot_target_idx,
            "fewshot_source": fewshot_src,
            "fewshot_num": num_fewshot,
            "ctx": ctx,
        }
        return ctx, logging_info

    def construct_requests(self, doc: dict, ctx: str):
        """Uses RequestFactory to construct Requests and returns an iterable of
        Requests which will be sent to the LM.

        Args:
            doc (dict):
                The document as returned from training_docs, validation_docs, or
                test_docs.
            ctx (str):
                The context string, generated by fewshot_context. This includes
                the natural language description, as well as the few shot examples,
                and the question part of the document for `doc`.
            args (dict):
                The specifics of the context, including number of few shots.

        Returns:
            An iterable of `Request` objects.
        """
        return rf.greedy_until(ctx, {"until": ["\n"]})

    def process_results(
        self, doc: dict, results: list
    ) -> Union[dict, Tuple[dict, dict]]:
        """Take a single document and the LM results and evaluates, returning a
        dict where keys are the names of sub-metrics and values are the values of
        the metric for that one document.

        NOTE: This function automates processing by using the `promptsource`
        metadata to determine the metric.

        Args:
            doc (dict):
                The document as returned from training_docs, validation_docs, or
                test_docs.
            results (list):
                The results of the requests created in construct_requests.

        Returns:
            A dict of metric results.
        """
        answer_choices_list = self.prompt_template.get_answer_choices_list(doc)
        target = self.doc_to_target(doc)
        if answer_choices_list:
            # If answer_choices_list, then this is a ranked choice prompt.
            # NOTE: In the future, target could be a list of strings.
            assert isinstance(target, list) and len(target) == 1
            target = target[0].strip()
            target_idx = answer_choices_list.index(target)

            pred = answer_choices_list[np.argmax(results)]
            out = {}

            for metric in self.prompt_template.metadata.metrics:
                if metric not in self.CONFIGURED_RANKED_CHOICE_PS_METRICS:
                    logger.warning(
                        f"Unexpected metric: `{metric}`. Add it, or use a task-specific solution."
                    )
                if metric == "Accuracy":
                    out["acc"] = pred == target
                    # Byte-length normalization.
                    completion_len = np.array(
                        [float(len(i)) for i in answer_choices_list]
                    )
                    out["acc_norm"] = (
                        1.0
                        if np.argmax(results / completion_len) == target_idx
                        else 0.0
                    )
            # TODO: Add metrics here.
        else:
            # If not, then this is a generation prompt.
            # NOTE: In the future, target will be a list of strings.
            assert isinstance(target, list)
            pred = results[0].strip()
            out = {}
            for metric in self.prompt_template.metadata.metrics:
                if metric not in self.CONFIGURED_GENERATION_PS_METRICS:
                    logger.warning(
                        f"Unexpected metric: `{metric}`. Add it, or use a task-specific solution."
                    )
                if metric == "BLEU":
                    out["bleu"] = (target, pred)
                elif metric == "ROUGE":
                    # TODO: This computes all rouge sub-metrics. Find a generic
                    # way to handle user specified rouge sub-metrics to avoid extra
                    # compute.
                    rouge_scores = rouge(target, pred)
                    # Flatten rouge score dict.
                    rouge_scores = utils.flatten(rouge_scores)
                    # Merge all the rouge-type scores into the `out` dict.
                    out = {**out, **rouge_scores}
                elif metric == "SARI":
                    out["sari"] = sari(self.doc_to_rawtext(doc), pred, target)

        # TODO: Wrap process results s.t. override impl do not
        # override the save examples.
        if self.save_examples:
            example = {
                "pred": pred,
                "target": target,
                "answer_choices_list": answer_choices_list,
            }
            return out, example
        return out

    def aggregation(self) -> Mapping[str, Callable]:
        out = {}
        for metric in self.prompt_template.metadata.metrics:
            if metric == "Accuracy":
                out["acc"] = mean
                out["acc_norm"] = mean
            elif metric == "BLEU":
                out["bleu"] = bleu
            elif metric == "ROUGE":
                # TODO: Find a generic way to handle user specified rouge metrics.
                out["rouge1_precision"] = mean
                out["rouge1_recall"] = mean
                out["rouge1_fmeasure"] = mean

                out["rouge2_precision"] = mean
                out["rouge2_recall"] = mean
                out["rouge2_fmeasure"] = mean

                out["rougeL_precision"] = mean
                out["rougeL_recall"] = mean
                out["rougeL_fmeasure"] = mean

                out["rougeLsum_precision"] = mean
                out["rougeLsum_recall"] = mean
                out["rougeLsum_fmeasure"] = mean
            elif metric == "SARI":
                out["sari"] = mean
        return out

    def higher_is_better(self) -> Mapping[str, bool]:
        out = {}
        for metric in self.prompt_template.metadata.metrics:
            if metric == "Accuracy":
                out["acc"] = True
                out["acc_norm"] = True
            elif metric == "BLEU":
                out["bleu"] = True
            elif metric == "ROUGE":
                # TODO: Find a generic way to handle user specified rouge metrics.
                out["rouge1_precision"] = True
                out["rouge1_recall"] = True
                out["rouge1_fmeasure"] = True

                out["rouge2_precision"] = True
                out["rouge2_recall"] = True
                out["rouge2_fmeasure"] = True

                out["rougeL_precision"] = True
                out["rougeL_recall"] = True
                out["rougeL_fmeasure"] = True

                out["rougeLsum_precision"] = True
                out["rougeLsum_recall"] = True
                out["rougeLsum_fmeasure"] = True
            elif metric == "SARI":
                out["sari"] = True
        return out

class GEMWikiLinguaBase(PromptSourceTask):
    VERSION = 1
    DATASET_PATH = dataset_paths["wikilingua"] if "wikilingua" in dataset_paths.keys() else "wikilingua"
    DATASET_NAME = "wikilingua"

    def has_training_docs(self):
        return True

    def has_validation_docs(self):
        return True

    def has_test_docs(self):
        return False

    def training_docs(self):
        if self.has_training_docs():
            return self.dataset["train"].filter(lambda doc: doc["article"]["document"] != [] and doc["article"]["summary"] != [])

    def validation_docs(self):
        if self.has_validation_docs():
            return self.dataset["train"].filter(lambda doc: doc["article"]["document"] != [] and doc["article"]["summary"] != [])#self.dataset["validation"]

    def test_docs(self):
        if self.has_test_docs():
            return self.dataset["sampled_test"]

    def max_generation_length(self):
        return 64


class GEMWikiLinguaAr(GEMWikiLinguaBase):
    LANG = "ar"


class GEMWikiLinguaCs(GEMWikiLinguaBase):
    LANG = "cs"


class GEMWikiLinguaDe(GEMWikiLinguaBase):
    LANG = "de"


class GEMWikiLinguaEn(GEMWikiLinguaBase):
    LANG = "en"
    LANG_DATASET = "english"

    TEMPLATE = """{document}

      ===
      
      Write a summary of the text above: """

    def doc_to_text(self, doc: dict) -> str:
        try:
            text = self.TEMPLATE.format(document=doc["article"]["document"][0])
        except IndexError:
            breakpoint()
        return text

    def doc_to_target(self, doc: dict) -> List[str]:
        return " ".join(doc["article"]["summary"])

class GEMWikiLinguaEs(GEMWikiLinguaBase):
    LANG = "es"
    LANG_DATASET = "spanish"


class GEMWikiLinguaFr(GEMWikiLinguaBase):
    LANG = "fr"


class GEMWikiLinguaHi(GEMWikiLinguaBase):
    LANG = "hi"


class GEMWikiLinguaId(GEMWikiLinguaBase):
    LANG = "id"


class GEMWikiLinguaIt(GEMWikiLinguaBase):
    LANG = "it"


class GEMWikiLinguaJa(GEMWikiLinguaBase):
    LANG = "ja"


class GEMWikiLinguaKo(GEMWikiLinguaBase):
    LANG = "ko"


class GEMWikiLinguaNl(GEMWikiLinguaBase):
    LANG = "nl"


class GEMWikiLinguaPt(GEMWikiLinguaBase):
    LANG = "pt"


class GEMWikiLinguaRu(GEMWikiLinguaBase):
    LANG = "ru"


class GEMWikiLinguaTh(GEMWikiLinguaBase):
    LANG = "th"


class GEMWikiLinguaTr(GEMWikiLinguaBase):
    LANG = "tr"


class GEMWikiLinguaVi(GEMWikiLinguaBase):
    LANG = "vi"


class GEMWikiLinguaZh(GEMWikiLinguaBase):
    LANG = "zh"


WIKILINGUA_TASKS = [
    GEMWikiLinguaAr,
    GEMWikiLinguaCs,
    GEMWikiLinguaDe,
    GEMWikiLinguaEn,
    GEMWikiLinguaEs,
    GEMWikiLinguaFr,
    GEMWikiLinguaHi,
    GEMWikiLinguaId,
    GEMWikiLinguaIt,
    GEMWikiLinguaJa,
    GEMWikiLinguaKo,
    GEMWikiLinguaNl,
    GEMWikiLinguaPt,
    GEMWikiLinguaRu,
    GEMWikiLinguaTh,
    GEMWikiLinguaTr,
    GEMWikiLinguaVi,
    GEMWikiLinguaZh,
]


def construct_tasks() -> typing.Dict[str, GEMWikiLinguaBase]:
    """
    Returns a dictionary of tasks keyed by task name, for example:
        "GEM/wiki_lingua_ar"
    will dispatch to the GEM WikiLingua Arabic class.
    """
    tasks = {}
    for task_class in WIKILINGUA_TASKS:
        benchmark = task_class.DATASET_NAME
        lang = task_class.LANG
        tasks[f"{benchmark}_{lang}"] = task_class
    return tasks
