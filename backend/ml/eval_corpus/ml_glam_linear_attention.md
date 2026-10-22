# GLAM: Gated Linear Attention with Memory for Efficient Language Modelling

## Abstract

Softmax attention gives transformers their quality but makes generation memory grow with the length of the context. Linear attention removes the softmax and replaces it with a kernel feature map, so that a recurrent state of fixed size can summarise the past. In practice linear attention models fall behind softmax models on recall-heavy tasks. We introduce GLAM, a decoder that adds a data-dependent forget gate and a small exact-attention memory of 64 slots to linear attention. GLAM-1.3B matches a softmax transformer of the same size on perplexity while generating 3.2 times faster at a context of 32,000 tokens.

## 1. Background

In softmax attention, each new token compares its query with the keys of all earlier tokens, so a model that has produced n tokens must keep n key and value vectors in its cache. Linear attention rewrites the attention score as a dot product of feature maps, φ(q)·φ(k), which allows the sum over past tokens to be accumulated into a matrix-valued state. The state has the same size no matter how long the context is, which makes generation cost constant per token.

The weakness of this approach is that the state is a lossy compression. Associative recall tests, in which a model must retrieve a value that was paired with a key thousands of tokens earlier, expose the problem: a pure linear attention model of 1.3 billion parameters answers only 41% of recall probes correctly at a distance of 8,000 tokens.

## 2. The GLAM layer

### 2.1 Forget gate

GLAM multiplies the recurrent state by a forget gate before adding each new key-value outer product. The gate is computed from the current token with a sigmoid, so the model can decide to keep the state when it reads filler text and to overwrite it when a new topic begins. We found it important to initialise the gate bias to 3.0, which makes the gate start close to one and prevents the state from being erased early in training.

### 2.2 Exact memory slots

Alongside the compressed state, each layer keeps 64 memory slots that store exact key and value vectors. A lightweight scorer decides which tokens are written to the slots; when the slots are full, the entry with the lowest accumulated attention is evicted. At read time, the query attends with a softmax over the 64 slots and the result is added to the linear attention output. The slots cost a fixed 64 vectors per layer, so memory stays constant.

### 2.3 Model sizes

We train three sizes: GLAM-350M, GLAM-760M and GLAM-1.3B, each on 100 billion tokens of a filtered web and code mixture with a context length of 4,096 during pre-training. The 1.3B model has 24 layers and a model dimension of 2,048. All models use the same tokenizer with a vocabulary of 50,000 entries.

## 3. Results

### 3.1 Language modelling

On our held-out validation set, GLAM-1.3B reaches a perplexity of 10.9, against 10.8 for a softmax transformer trained on the same data and 11.6 for linear attention without gates or memory. The gap between GLAM and the softmax model is within the run-to-run variance we observed across three seeds.

### 3.2 Recall

The exact memory slots matter most for recall. At a distance of 8,000 tokens, GLAM-1.3B answers 87% of associative recall probes, compared with 41% for ungated linear attention and 93% for the softmax transformer. Removing the memory slots but keeping the forget gate gives 58%, which shows that gating alone does not solve recall.

### 3.3 Speed

Because neither the state nor the memory grows with the context, GLAM decodes at a constant 2.1 milliseconds per token on one accelerator. At a context of 32,000 tokens the softmax model needs 6.7 milliseconds per token, making GLAM 3.2 times faster. Pre-filling a long prompt is slower for GLAM than for a softmax model with an optimised kernel, because the recurrent scan is harder to parallelise.

## 4. Limitations and future work

GLAM still trails softmax attention on tasks that need precise copying of long spans, such as reproducing a 200-token passage verbatim. The eviction rule for the memory slots is heuristic; a learned eviction policy could improve recall further. We also have not trained models larger than 1.3 billion parameters, so it is unclear whether the gap to softmax attention closes or widens at scale. Finally, our speed measurements use a single accelerator; serving many users at once changes the trade-offs, because softmax models can batch requests more efficiently during pre-fill.
