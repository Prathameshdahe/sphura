# LatticeFormer: Block-Sparse Attention for Long-Document Understanding

## Abstract

Transformer encoders scale quadratically with sequence length because every token attends to every other token. We present LatticeFormer, an encoder that replaces dense self-attention with a block-sparse lattice pattern combining local windows, strided relay tokens and a small set of global summary tokens. On the LongDocQA benchmark with inputs of 16,384 tokens, LatticeFormer-Base reaches 71.4 F1 while using 5.8 times less attention memory than a dense baseline truncated to 4,096 tokens. The relay tokens are the key ingredient of the design.

## 1. Introduction

Many real documents, such as contracts, clinical notes, patents and scientific papers, are far longer than the 512 or 4,096 tokens that standard encoders accept. The usual workaround is to cut the document into overlapping windows and process each one independently, which breaks reasoning that spans distant paragraphs. Sparse attention patterns reduce the cost of attention, but fixed local windows struggle to move information across the whole sequence in a single layer.

LatticeFormer is built on a simple observation: information only needs a short path between any two tokens, not a direct edge. If every block can reach a relay token, and every relay token can reach every other relay token, then any two tokens are connected in at most three hops. We call this arrangement a lattice.

## 2. Method

### 2.1 Block layout

The input sequence is divided into blocks of 128 tokens. Each token attends densely to its own block and to the two neighbouring blocks, giving a local receptive field of 384 tokens. In addition, the first token of every block is promoted to a relay token. Relay tokens attend to each other across the entire sequence, which costs O(n²/b²) operations for block size b instead of O(n²).

### 2.2 Global summary tokens

We prepend 16 learned global summary tokens that attend to and are attended by every position. Unlike the relay tokens, summary tokens are not tied to a position in the text; they behave like a small scratchpad that collects document-level evidence such as the topic or the names of the parties in a contract.

### 2.3 Training recipe

LatticeFormer-Base has 12 layers, a hidden size of 768 and 12 attention heads, for 149 million parameters. It is initialised from a RoBERTa-style checkpoint and pre-trained for a further 60,000 steps on long documents using a masked-language-modelling objective with a 15% masking rate. Position embeddings beyond 512 are initialised by copying the first 512 embeddings repeatedly, a trick that cuts the warm-up time roughly in half. Training used 32 accelerators for 9 days.

## 3. Experiments

### 3.1 Benchmarks

We evaluate on three long-input tasks. LongDocQA contains 12,000 extractive questions over legal and financial filings with a median length of 11,200 tokens. PatentCls asks the model to assign one of 64 classification codes to a full patent. ClinicalLink requires linking medication mentions to diagnoses that may appear pages apart.

### 3.2 Results

On LongDocQA, LatticeFormer-Base scores 71.4 F1 compared with 66.2 F1 for a dense RoBERTa baseline that sees only the first 4,096 tokens, and 68.9 F1 for a sliding-window baseline. On PatentCls it reaches 82.7% accuracy. The largest gain appears on ClinicalLink, where the relay tokens allow the model to connect a medication on page two with a diagnosis on page nine; here LatticeFormer improves recall from 0.58 to 0.71.

Throughput measurements were taken on a single accelerator with batch size 8. At 16,384 tokens, LatticeFormer processes 41 documents per second, while the dense model runs out of memory beyond 6,144 tokens.

### 3.3 Ablations

Removing relay tokens reduces LongDocQA F1 from 71.4 to 66.5, confirming that cross-block routing matters more than the size of the local window. Doubling the block size to 256 tokens improves F1 by only 0.3 points while increasing memory by 41%. Removing the global summary tokens costs 1.8 F1 points, with the largest drop on questions that ask about the document as a whole.

## 4. Limitations

LatticeFormer is an encoder and does not generate text. The block layout assumes that documents are read left to right, so tables that span several blocks can be split in unhelpful places. Finally, all of our benchmarks are in English; we have not measured how well the relay pattern transfers to languages with very different token lengths.

## 5. Conclusion

A lattice of local blocks, relay tokens and global summaries gives an encoder access to sixteen thousand tokens at a fraction of the memory cost of dense attention. Compared with chunking a document into independent windows, the model can follow references between distant sections, which matters most in legal and clinical text. We release code and checkpoints under the Apache 2.0 licence, together with the scripts used to build LongDocQA from public filings.
