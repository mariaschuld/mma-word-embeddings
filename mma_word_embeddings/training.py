# This file contains a wrapper class for word2vec models training word trained_embeddings
import os
import numpy as np
from gensim.models import Word2Vec
from random import seed, shuffle


class DataGenerator(object):
    def __init__(self, path_to_data,
                 share_of_original_data,
                 chunk_size,
                 random_buffer_size,
                 data_seed=42):
        """Iterator that loads a lines from a file.
        Args:
            path_to_data (str): Full path to a data file with one preprocessed sentence/document per line.
            share_of_original_data (float):  and picks each line with probability share_of_original_data, which
                effectively results in a dataset with approx n_data*share_of_original_data samples
            chunk_size (int): Return so many lines from the random buffer at once before filling it up again. Larger
                chunk sizes speed up training, but decrease randomness.
            random_buffer_size (int): Keep so many lines from the data file in a buffer which is shuffled before
                returning the samples in a chunk. Higher values take more RAM but lead to more randomness
                when sampling the data. A value equal to the number of all samples would lead to perfectly
                random samples.
        """
        if chunk_size > random_buffer_size:
            raise ValueError("Chunk size cannot be larger than the buffer size.")

        self.path_to_data = path_to_data
        self.share_of_original_data = share_of_original_data
        self.chunk_size = chunk_size
        self.random_buffer_size = random_buffer_size

        # fix the seed of data sampling, so that multiple creations of this iterator
        # during training will create
        # the same random selection of lines
        seed(data_seed)

    def __iter__(self):

        # load initial buffer
        buffer = []
        with open(self.path_to_data, "r") as f:

            # fill buffer for the first time
            for i in range(self.random_buffer_size):
                line = f.readline().strip().split(" ")
                buffer.append(line)

            reached_end = False
            while not reached_end:

                # randomise the buffer
                shuffle(buffer)

                # remove and return chunk from buffer
                for i in range(self.chunk_size):
                    # separate non-bootstrap case here for speed
                    if self.share_of_original_data == 1.0:
                        yield buffer.pop(0)
                    else:
                        # randomly decide whether this line is in
                        # the bootstrapped data
                        if np.random.rand() > self.share_of_original_data:
                            # remove anyways
                            buffer.pop(0)
                            continue
                        else:
                            yield buffer.pop(0)

                # fill up the buffer with a fresh chunk
                for i in range(self.chunk_size):
                    line = f.readline()
                    if not line:
                        reached_end = True
                        break
                    else:
                        buffer.append(line.strip().split(" "))

            # if end of file has been reached
            # yield all elements left in the buffer
            # in random order
            shuffle(buffer)
            for el in buffer:
                yield el


def train_word2vec_model(
        path_training_data,
        path_description,
        output_path,
        hyperparameters={},
        normalize=True,
        n_models=1,
        share_of_original_data=1.,
        chunk_size=10000,
        random_buffer_size=100000,
        path_pretraining_data=None,
        data_seed=None,
):
    """Trains a single embedding or an ensemble of embeddings.

    Args:
        path_training_data (str): location of training data, one sentence/document per line
        path_description (str): location of description file for training data
        output_path (str): where to save the model and description file; does not include an ending (.emb will
            be automatically added)
        hyperparameters (dict): dictionary of hyperparameters that are directly fed into Word2Vec model
        normalize (bool): whether to normalize the word vectors
        n_models (int): number of models to train
        share_of_original_data (float): each line loaded from the data file is discarded
            with this ratio; use 1. to use all data
        chunk_size (int): Return so many lines from the random buffer at once before filling it up again. Larger
            chunk sizes speed up training, but decrease randomness.
        random_buffer_size (int): Keep so many lines from the data file in a buffer which is shuffled before
            returning the samples in a chunk. Higher values take more RAM but lead to more randomness
            when sampling the data. A value equal to the number of all samples would lead to perfectly
            random samples.
        path_pretraining_data (str): if model should get pre-trained, specify this path to the pretraining data set;
            the full dataset will be used for pre-training
        data_seed (int): Random seed set for sampling. When more than one model is created, the ith model
         will use data_seed + i as a seed for the data.
    """

    # check paths before starting costly training ---------
    # INPUT paths
    if not os.path.isfile(path_training_data):
        raise ValueError(f"Unknown path to training data {path_training_data}")
    if path_pretraining_data is not None and not os.path.isfile(path_pretraining_data):
        raise ValueError(f"Unknown path to pretraining data {path_pretraining_data}")
    if not os.path.isfile(path_description):
        raise ValueError(f"Unknown path to data description file {path_description}")

    # OUTPUT paths
    dirname = os.path.dirname(output_path)
    if not os.path.exists(dirname):
        raise ValueError(f"Directory {dirname} does not exist.")
    if n_models == 1:
        path_out = output_path + "-" + ".emb"
        path_description_out = output_path + "_description.txt"
        if os.path.isfile(path_out):
            raise ValueError("Path {} for description already exists.".format(path_out))
        if os.path.isfile(path_description_out):
            raise ValueError("Path {} for description already exists.".format(path_description_out))
    else:
        for m in range(n_models):
            path_out = output_path + "-" + str(m) + ".emb"
            path_description_out = output_path + "-" + str(m) + "_description.txt"
            if os.path.isfile(path_out):
                raise ValueError("Path {} for description already exists.".format(path_out))
            if os.path.isfile(path_description_out):
                raise ValueError("Path {} for description already exists.".format(path_description_out))
    # ---------------

    for m in range(n_models):

        print("Training model ", m + 1)

        training_generator = DataGenerator(path_training_data,
                                           share_of_original_data,
                                           chunk_size,
                                           random_buffer_size,
                                           data_seed + m)

        if path_pretraining_data is None:
            # do not pretrain
            model = Word2Vec(sentences=training_generator, **hyperparameters)

        else:
            pretraining_generator = DataGenerator(path_pretraining_data,
                                                  1.0,
                                                  chunk_size,
                                                  random_buffer_size,
                                                  data_seed + m)
            model = Word2Vec(sentences=pretraining_generator, **hyperparameters)
            model.build_vocab(training_generator, update=True)
            model.train(corpus_iterable=training_generator, total_examples=model.corpus_count, epochs=model.epochs)

        if normalize:
            # normalise the word vectors
            model.wv.init_sims(replace=True)
        # extract embedding
        emb = model.wv

        # save the current embedding
        if n_models == 1:
            path_out = output_path + ".emb"
            path_description_out = output_path + "_description.txt"

        else:
            path_out = output_path + "-" + str(m) + ".emb"
            path_description_out = output_path + "-" + str(m) + "_description.txt"

        emb.save(path_out)

        # save description
        with open(path_description) as f:
            description = f.readlines()
            description = "".join(description)
        log = "The following training data was used:\n\n{}\n".format(description)
        if path_pretraining_data is not None:
            log += f"Model was pretrained with data loaded from: {path_pretraining_data}."
        log += "Used {}% of original data for training.\n".format(100 * share_of_original_data)
        log += "Used a random buffer size of {} lines and chunks of size {}.\n".format(random_buffer_size, chunk_size)
        log += f"Used the data seed {data_seed} \n."
        log += "The model generating the embedding was trained with the following " \
               "hyperparameters: \n {}\n".format(hyperparameters)
        log += f"Word vectors were normalized: {normalize}"

        with open(path_description_out, "w") as f:
            f.write(log)


