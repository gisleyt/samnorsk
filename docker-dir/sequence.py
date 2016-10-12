





def getPermutations(sentence_length):

    indices = range(sentence_length)
    perm = []
    idx = 0

    while (True):
        if (idx >= sentence_length):
            break
        perm.append((indices[idx], indices[idx]))

        if sentence_length > idx + 1:
            perm.append((indices[idx], indices[idx + 1]))
        idx += 1
    return perm


def rec(ts1, ts2, sequences, results):
    if (len(ts1) == 0) and len(ts2) == 0:
        #Sucess - base case!
        results.append(str(sequences))
        return
    if (len(ts1) == 0 and len(ts2) != 0) or (len(ts1) != 0 and len(ts2) == 0):
        #Failure
        return

    if (len(ts1) > (len(ts2) * 2) + 1) or len(ts2) > (len(ts1) * 2 + 1):
        # Early failure, will not succeed.
        return

    if len(ts1) >= 1 and len(ts2) >= 1:

        seq_copy = sequences[:]
        seq_copy.append(str(ts1[0]) + "->" + str(ts2[0]))
        rec(ts1[2:], ts2[2:], seq_copy, results)

        if len(ts1) > 1:
            seq_copy2 = sequences[:]
            seq_copy2.append(str(ts1[1]) + "->" + str(ts2[0]))
            rec(ts1[4:], ts2[2:], seq_copy2, results)

        if len(ts2) > 1:
            seq_copy3 = sequences[:]
            seq_copy3.append(str(ts1[0]) + "->" + str(ts2[1]))
            rec(ts1[2:], ts2[4:], seq_copy3, results)


def main():

    s_1 = getPermutations(20)
    s_2 = getPermutations(20)

    foo = []
    results = []
    #print s_1
    #print s_2
    rec(s_1, s_2, foo, results)
    #print results
    print len(results)
    print len(list(set(results)))
    #for res in results:
    #    print res






if __name__ == '__main__':
    main()