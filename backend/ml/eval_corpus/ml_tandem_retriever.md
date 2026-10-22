# Tandem: Training Dense Passage Retrievers with Mined Hard Negatives

## Abstract

Dense retrievers encode questions and passages into vectors and retrieve by nearest-neighbour search. Their quality depends heavily on the negative passages used during contrastive training. We describe Tandem, a two-stage recipe in which a first retriever mines hard negatives that a cross-encoder then filters for false negatives before a second retriever is trained. On the OpenFacts benchmark, Tandem improves top-20 retrieval accuracy from 78.4% to 84.1% over a retriever trained with in-batch negatives only.

## 1. Motivation

A dual encoder is trained to give a question a higher similarity with its gold passage than with any negative passage. Random negatives are too easy: the model learns to separate a question about volcanoes from a passage about tax law, which teaches it little. Hard negatives, such as passages about a different volcano, force the model to attend to the details that actually distinguish relevant from irrelevant text.

Mining hard negatives with the retriever itself introduces a new problem. Some of the passages it ranks highly are not negatives at all; they answer the question but were never labelled. Training the model to push these false negatives away teaches it to ignore genuinely relevant evidence. In a manual audit of 500 mined negatives, annotators judged 18% to be relevant to the question.

## 2. Method

### 2.1 Stage one

The first-stage retriever is a BERT-base dual encoder trained for 40 epochs with in-batch negatives and a batch size of 512. We use it to retrieve the top 100 passages for every training question from the full corpus of 21 million passages.

### 2.2 False-negative filtering

A cross-encoder reads each question together with each mined passage and outputs a relevance probability. Passages scoring above 0.9 are treated as unlabelled positives and removed from the negative pool, while passages scoring below 0.1 are kept as hard negatives. Passages in between are discarded because the cross-encoder is uncertain about them. This filter removes about one in six mined passages.

### 2.3 Stage two

The second-stage retriever is initialised from the first and trained for 10 more epochs. Each training example contains one positive passage, seven filtered hard negatives and all other passages in the batch as additional negatives. We use a temperature of 0.05 in the contrastive loss; higher temperatures made the model less sensitive to the hard negatives.

## 3. Evaluation

### 3.1 Setup

OpenFacts contains 8,757 test questions written by annotators who could see a Wikipedia paragraph, which makes the questions closer in wording to their passages than real user queries are. To test robustness we also report results on ParaQueries, where every question was rewritten by a second annotator to avoid the words used in the passage.

### 3.2 Results

Tandem reaches 84.1% top-20 accuracy on OpenFacts and 79.6% on ParaQueries. The BM25 baseline reaches 71.2% on OpenFacts but only 52.3% on ParaQueries, which shows how strongly lexical retrieval depends on shared vocabulary between the question and the passage. Without the cross-encoder filter, the second stage reaches 82.2% on OpenFacts, so filtering false negatives accounts for roughly a third of the total improvement.

### 3.3 Hybrid retrieval

Combining Tandem with BM25 through reciprocal rank fusion adds another 1.9 points of top-20 accuracy on OpenFacts. The gain is concentrated on questions that contain rare identifiers, such as product codes or chemical names, which dense encoders tend to blur into similar-looking tokens. A cross-encoder that re-scores the fused top 50 adds a further 2.4 points at the top-5 cut-off, but it increases query latency roughly tenfold.

## 4. Discussion

The cross-encoder filter is expensive: scoring 100 passages for each of 79,000 training questions took 31 GPU-hours. Cheaper filters, such as agreement between two independently trained retrievers, recover most of the benefit at a tenth of the cost. Tandem also inherits the biases of the corpus: questions about recent events whose passages are missing from the index cannot be answered by any retriever, however well it is trained.

We also observed that the retriever learns surface shortcuts when the training questions are written by people who can see the passage. Mixing in a small share of paraphrased questions during the second stage, about 10% of the training set, improved ParaQueries accuracy by 1.7 points without hurting OpenFacts. Future work will study how much of this benefit comes from vocabulary diversity and how much from longer, more natural questions.
