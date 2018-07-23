# -*- coding: utf-8 -*-
import os
import sys
import time
from optparse import OptionParser

from arksemaforeval import *
from dynet import *
from evaluation import *
from raw_data import make_data_instance


optpr = OptionParser()
optpr.add_option("--mode", dest="mode", type="choice", choices=["train", "test", "refresh", "predict"], default="train")
optpr.add_option("-n", "--model_name", help="Name of model directory to save model to.")
optpr.add_option("--nodrop", action="store_true", default=False)
optpr.add_option("--nowordvec", action="store_true", default=False)
optpr.add_option("--raw_input", type="str", metavar="FILE")
(options, args) = optpr.parse_args()

model_dir = "logs/{}/".format(options.model_name)
model_file_name = "{}best-targetid-{}-model".format(model_dir, VERSION)
if not os.path.exists(model_dir):
    os.makedirs(model_dir)

train_conll = TRAIN_FTE

USE_DROPOUT = not options.nodrop
if options.mode in ["test", "predict"]:
    USE_DROPOUT = False
USE_WV = not options.nowordvec

sys.stderr.write("\nCOMMAND: " + " ".join(sys.argv) + "\n")
sys.stderr.write("\nPARSER SETTINGS\n_____________________\n")
sys.stderr.write("PARSING MODE:   \t" + options.mode + "\n")
sys.stderr.write("USING DROPOUT?  \t" + str(USE_DROPOUT) + "\n")
sys.stderr.write("USING WORDVECS? \t" + str(USE_WV) + "\n")
if options.mode in ["train", "refresh"]:
    sys.stderr.write("VALIDATED MODEL WILL BE SAVED TO\t{}\n".format(model_file_name))
else:
    sys.stderr.write("MODEL USED FOR TEST / PREDICTION:\t{}\n".format(model_file_name))
sys.stderr.write("_____________________\n")

UNK_PROB = 0.1
DROPOUT_RATE = 0.01

TOKDIM = 100
POSDIM = 100
LEMDIM = 100

INPDIM = TOKDIM + POSDIM + LEMDIM

LSTMINPDIM = 100
LSTMDIM = 100
LSTMDEPTH = 2
HIDDENDIM = 100


def combine_examples(corpus_ex):
    """
    Target ID needs to be trained for all targets in the sentence jointly, as opposed to
    frame and arg ID. Returns all target annotations for a given sentence.
    """
    combined_ex = [corpus_ex[0]]
    for ex in corpus_ex[1:]:
        if ex.sent_num == combined_ex[-1].sent_num:
            current_sent = combined_ex.pop()
            target_frame_dict = current_sent.targetframedict.copy()   
            target_frame_dict.update(ex.targetframedict)
            current_sent.targetframedict = target_frame_dict
            combined_ex.append(current_sent)
            continue
        combined_ex.append(ex)
    return combined_ex

train_examples, _, _ = read_conll(train_conll)
combined_train = combine_examples(train_examples)
sys.stderr.write( "{} combined into {} examples for Target ID.\n".format(len(train_examples), len(combined_train)))

# Need to read all LUs before locking the dictionaries.
target_lu_map, lu_names = create_target_lu_map()
post_train_lock_dicts()

if USE_WV:
    wvs = get_wvec_map()
    PRETDIM = len(wvs.values()[0])
    sys.stderr.write("using pretrained embeddings of dimension {}\n".format(PRETDIM))

lock_dicts() 
UNKTOKEN = VOCDICT.getid(UNK)

sys.stderr.write("# Words in vocab: " + str(VOCDICT.size()) + "\n")
sys.stderr.write("# POS tags: " + str(POSDICT.size()) + "\n")
sys.stderr.write("# Lemmas: " + str(LEMDICT.size()) + "\n")

if options.mode in ["train", "refresh"]:
    dev_examples, _, _ = read_conll(DEV_CONLL)
    combined_dev = combine_examples(dev_examples)
    sys.stderr.write("unknowns in dev\n\n_____________________\n")
    out_conll_file = "{}predicted-{}-targetid-dev.conll".format(model_dir, VERSION)
elif options.mode  == "test":
    dev_examples, m, t = read_conll(TEST_CONLL)
    combined_dev = combine_examples(dev_examples)
    sys.stderr.write("unknowns in test\n\n_____________________\n")
    out_conll_file = "{}predicted-{}-targetid-test.conll".format(model_dir, VERSION)
elif options.mode == "predict":
    assert options.raw_input is not None
    with open(options.raw_input, "r") as fin:
        instances = [make_data_instance(line, i) for i,line in enumerate(fin)]
    out_conll_file = "{}predicted-targets.conll".format(model_dir)
else:
    raise Exception("invalid parser mode", options.mode)

sys.stderr.write("# unseen, unlearnt test words in vocab: " + str(VOCDICT.num_unks()) + "\n")
sys.stderr.write("# unseen, unlearnt test POS tags: " + str(POSDICT.num_unks()) + "\n")
sys.stderr.write("# unseen, unlearnt test lemmas: " + str(LEMDICT.num_unks()) + "\n")


def get_fn_pos_by_rules(pos, token):
    """
    Rules for mapping NLTK part of speech tags into FrameNet tags, based on co-occurrence
    statistics, since there is not a one-to-one mapping.
    """
    if pos[0] == "v" or pos in ["rp", "ex", "md"]:  # Verbs
        rule_pos = "v"
    elif pos[0] == "n" or pos in ["$", ":", "sym", "uh"]:  # Nouns
        rule_pos = "n"
    elif pos[0] == "j" or pos in ["ls", "pdt", "rbr", "rbs", "prp"]:  # Adjectives
        rule_pos = "a"
    elif pos == "cc":  # Conjunctions
        rule_pos = "c"
    elif pos in ["to", "in"]:  # Prepositions
        rule_pos = "prep"
    elif pos in ["dt", "wdt"]:  # Determinors
        rule_pos = "art"
    elif pos in ["rb", "wrb"]:  # Adverbs
        rule_pos = "adv"
    elif pos == "cd":  # Cardinal Numbers
        rule_pos = "num"
    else:
        raise Exception("Rule not defined for part-of-speech word", pos, token)
    return rule_pos


def check_if_potential_target(lemma):
    """
    Simple check to see if this is a potential position to even consider, based on
    the LU index provided under FrameNet. Note that since we use NLTK lemmas, 
    this might be lossy.
    """
    nltk_lem_str = LEMDICT.getstr(lemma)
    return nltk_lem_str in target_lu_map or nltk_lem_str.lower() in target_lu_map
        

def create_lexical_unit(lemma_id, pos_id, token_id):
    """
    Given a lemma ID and a POS ID (both lemma and POS derived from NLTK), 
    create a LexicalUnit object.
    If lemma is unknown, then check if token is in the LU vocabulary, and 
    use it if present (Hack).
    """
    nltk_lem_str = LEMDICT.getstr(lemma_id)
    if nltk_lem_str not in target_lu_map and nltk_lem_str.lower() in target_lu_map:
        nltk_lem_str = nltk_lem_str.lower()

    # Lemma is not in FrameNet, but it could be a lemmatization error.
    if nltk_lem_str == UNK:
        if VOCDICT.getstr(token_id) in target_lu_map:
            nltk_lem_str = VOCDICT.getstr(token_id)
        elif VOCDICT.getstr(token_id).lower() in target_lu_map:
            nltk_lem_str = VOCDICT.getstr(token_id).lower()
    assert nltk_lem_str in target_lu_map
    assert LUDICT.getid(nltk_lem_str) != LUDICT.getid(UNK)

    nltk_pos_str = POSDICT.getstr(pos_id)
    rule_pos_str = get_fn_pos_by_rules(nltk_pos_str.lower(), nltk_lem_str)
    rule_lupos = nltk_lem_str + "." + rule_pos_str

    # Lemma is not seen with this pos tag.
    if rule_lupos not in lu_names:
        # Hack: replace with anything the lemma is seen with.
        rule_pos_str = list(target_lu_map[nltk_lem_str])[0].split(".")[-1]
    return LexicalUnit(LUDICT.getid(nltk_lem_str), LUPOSDICT.getid(rule_pos_str))


model = Model()
trainer = SimpleSGDTrainer(model, 0.01)

v_x = model.add_lookup_parameters((VOCDICT.size(), TOKDIM))
p_x = model.add_lookup_parameters((POSDICT.size(), POSDIM))
l_x = model.add_lookup_parameters((LEMDICT.size(), LEMDIM))

if USE_WV:
    e_x = model.add_lookup_parameters((VOCDICT.size(), PRETDIM))
    for wordid in wvs:
        e_x.init_row(wordid, wvs[wordid])
    w_e = model.add_parameters((LSTMINPDIM, PRETDIM))
    b_e = model.add_parameters((LSTMINPDIM, 1))

w_i = model.add_parameters((LSTMINPDIM, INPDIM))
b_i = model.add_parameters((LSTMINPDIM, 1))

builders = [
    LSTMBuilder(LSTMDEPTH, LSTMINPDIM, LSTMDIM, model),
    LSTMBuilder(LSTMDEPTH, LSTMINPDIM, LSTMDIM, model),
]

w_z = model.add_parameters((HIDDENDIM, 2*LSTMDIM))
b_z = model.add_parameters((HIDDENDIM, 1))
w_f = model.add_parameters((2, HIDDENDIM))  # prediction: is a target or not.
b_f = model.add_parameters((2, 1))


def identify_targets(builders, tokens, postags, lemmas, gold_targets=None):
    """
    Target identification model, using bidirectional LSTMs, with a
    multilinear perceptron layer on top for classification.
    """
    renew_cg()
    train_mode = (gold_targets is not None)

    sentlen = len(tokens)
    emb_x = [v_x[tok] for tok in tokens]
    pos_x = [p_x[pos] for pos in postags]
    lem_x = [l_x[lem] for lem in lemmas]

    pw_i = parameter(w_i)
    pb_i = parameter(b_i)

    emb2_xi = [(pw_i * concatenate([emb_x[i], pos_x[i], lem_x[i]])  + pb_i) for i in xrange(sentlen)]
    if USE_WV:
        pw_e = parameter(w_e)
        pb_e = parameter(b_e)
        for i in xrange(sentlen):
            if tokens[i] in wvs:
                nonupdatedwv = e_x[tokens[i]]  # Prevent the pretrained embeddings from being updated.
                emb2_xi[i] = emb2_xi[i] + pw_e * nonupdatedwv + pb_e

    emb2_x = [rectify(emb2_xi[i]) for i in xrange(sentlen)]

    pw_z = parameter(w_z)
    pb_z = parameter(b_z)
    pw_f = parameter(w_f)
    pb_f = parameter(b_f)

    # Initializing the two LSTMs.
    if USE_DROPOUT and train_mode:
        builders[0].set_dropout(DROPOUT_RATE)
        builders[1].set_dropout(DROPOUT_RATE)
    f_init, b_init = [i.initial_state() for i in builders]

    fw_x = f_init.transduce(emb2_x)
    bw_x = b_init.transduce(reversed(emb2_x))

    losses = []
    predicted_targets = {}
    for i in xrange(sentlen):
        if not check_if_potential_target(lemmas[i]):
            continue
        h_i = concatenate([fw_x[i], bw_x[sentlen - i - 1]])
        score_i = pw_f * rectify(pw_z * h_i + pb_z) + pb_f
        if train_mode and USE_DROPOUT:
            score_i = dropout(score_i, DROPOUT_RATE)

        logloss = log_softmax(score_i, [0, 1])
        if not train_mode:
            is_target = np.argmax(logloss.npvalue())
        else:
            is_target = int(i in gold_targets)
        
        if int(np.argmax(logloss.npvalue())) != 0:
            predicted_targets[i] = (create_lexical_unit(lemmas[i], postags[i], tokens[i]), None)
        
        losses.append(pick(logloss, is_target))
    
    objective = -esum(losses) if losses else None
    return objective, predicted_targets


def print_as_conll(gold_examples, predicted_target_dict):
    """
    Creates a CoNLL object with predicted target and lexical unit.
    Spits out one CoNLL for each LU.
    """
    with codecs.open(out_conll_file, "w", "utf-8") as conll_file:
        for gold, pred in zip(gold_examples, predicted_target_dict):
            for target in sorted(pred):
                result = gold.get_predicted_target_conll(target, pred[target][0]) + "\n"
                conll_file.write(result)
        conll_file.close()


# Main method.
NUMEPOCHS = 100
PATIENCE = 25
EVAL_EVERY_EPOCH = 100
DEV_EVAL_EPOCH = 3 * EVAL_EVERY_EPOCH

best_dev_f1 = 0.0
if options.mode in ["refresh"]:
    sys.stderr.write("Reusing model from {} ...\n".format(model_file_name))
    model.populate(model_file_name)
    with open(os.path.join(model_dir, "best-dev-f1.txt"), "r") as fin:
        for line in fin:
            best_dev_f1 = float(line.strip())
    fin.close()
    sys.stderr.write("Best dev F1 so far = %.4f\n" % best_dev_f1)


if options.mode in ["train", "refresh"]:
    tagged = loss = 0.0
    train_result = [0.0, 0.0, 0.0]

    last_updated_epoch = 0

    for epoch in xrange(NUMEPOCHS):
        random.shuffle(combined_train)
        for idx, trex in enumerate(combined_train, 1):
            if idx % EVAL_EVERY_EPOCH == 0:
                trainer.status()
                _, _, trainf = calc_f(train_result)
                sys.stderr.write("%d loss = %.6f train f1 = %.4f\n" %(idx, loss/tagged, trainf))
                tagged = loss = 0.0
                train_result = [0.0, 0.0, 0.0]
            inptoks = []
            unk_replace_tokens(trex.tokens, inptoks, VOCDICT, UNK_PROB, UNKTOKEN)

            trex_loss, trexpred = identify_targets(
                builders, inptoks, trex.postags, trex.lemmas, gold_targets=trex.targetframedict.keys())
            trainex_result = evaluate_example_targetid(trex.targetframedict.keys(), trexpred)
            train_result = np.add(train_result, trainex_result)

            if trex_loss is not None:
                loss += trex_loss.scalar_value()
                trex_loss.backward()
                trainer.update()
            tagged += 1

            if idx % DEV_EVAL_EPOCH == 0:
                corpus_result = [0.0, 0.0, 0.0]
                devtagged = devloss = 0.0
                predictions = []
                for devex in combined_dev:
                    devludict = devex.get_only_targets()
                    dl, predicted = identify_targets(
                        builders, devex.tokens, devex.postags, devex.lemmas)
                    if dl is not None:
                        devloss += dl.scalar_value()
                    predictions.append(predicted)

                    devex_result = evaluate_example_targetid(devex.targetframedict.keys(), predicted)
                    corpus_result = np.add(corpus_result, devex_result)
                    devtagged += 1

                dev_p, dev_r, dev_f1 = calc_f(corpus_result)
                dev_tp, dev_fp, dev_fn = corpus_result
                sys.stderr.write("[dev epoch=%d] loss = %.6f "
                                 "p = %.4f (%.1f/%.1f) r = %.4f (%.1f/%.1f) f1 = %.4f"
                                 % (epoch, devloss/devtagged,
                                    dev_p, dev_tp, dev_tp + dev_fp,
                                    dev_r, dev_tp, dev_tp + dev_fn,
                                    dev_f1))
                if dev_f1 > best_dev_f1:
                    best_dev_f1 = dev_f1
                    with open(os.path.join(model_dir, "best-dev-f1.txt"), "w") as fout:
                        fout.write("{}\n".format(best_dev_f1))

                    sys.stderr.write(" -- saving to {}".format(model_file_name))
                    model.save(model_file_name)
                    print_as_conll(combined_dev, predictions)
                    
                    last_updated_epoch = epoch
                sys.stderr.write("\n")
        if epoch - last_updated_epoch > PATIENCE:
            sys.stderr.write("Ran out of patience, ending training.")
            break

elif options.mode == "test":
    model.populate(model_file_name)
    corpus_tp_fp_fn = [0.0, 0.0, 0.0]

    test_predictions = []

    for test_ex in combined_dev:
        _, predicted = identify_targets(builders, test_ex.tokens, test_ex.postags, test_ex.lemmas)

        tp_fp_fn = evaluate_example_targetid(test_ex.targetframedict.keys(), predicted)
        corpus_tp_fp_fn = np.add(corpus_tp_fp_fn, tp_fp_fn)

        test_predictions.append(predicted)

    test_tp, test_fp, test_fn = corpus_tp_fp_fn
    test_prec, test_rec, test_f1 = calc_f(corpus_tp_fp_fn)
    sys.stderr.write("[test] p = %.4f (%.1f/%.1f) r = %.4f (%.1f/%.1f) f1 = %.4f\n" %(
        test_prec, test_tp, test_tp + test_fp,
        test_rec, test_tp, test_tp + test_fn,
        test_f1))

    sys.stderr.write("Printing output in CoNLL format to {}\n".format(out_conll_file))
    print_as_conll(combined_dev, test_predictions)
    sys.stderr.write("Done!\n")

elif options.mode == "predict":
    model.populate(model_file_name)

    predictions = []
    for instance in instances:
        _, prediction = identify_targets(builders, instance.tokens, instance.postags, instance.lemmas)
        predictions.append(prediction)
    sys.stderr.write("Printing output in CoNLL format to {}\n".format(out_conll_file))
    print_as_conll(instances, predictions)
    sys.stderr.write("Done!\n")