from collections import defaultdict, Counter
import math
import bisect
import numpy, numpy.linalg
import multiprocessing

TOTAL_PAGES = 0

def tf_idf(term: str, doc_id: int, iid: defaultdict[str, list[(int, int)]], total_pages: int, term_frequency=None):
    postings = iid[term]

    if not term_frequency:
        position = bisect.bisect_left(postings, [doc_id])
        term_frequency = -1
        if postings[position][0] == doc_id:
            term_frequency = postings[position][1]
    
    doc_count = len(postings)

    return (1+ math.log(term_frequency)) * math.log(total_pages/doc_count) if term_frequency > 0 else 0


def get_intersection(intersection: list[(int, int)], new_term_postings) -> list[(int, int)]:
    '''
    index 0 should be the docid, index 1 should be the term frequency in the doc
    returns a list of postings - (docid, frequency of the new term inside doc)
    '''
    i = 0
    j = 0
    result = []
    while i < len(intersection) and j < len(new_term_postings):
        if intersection[i][0] == new_term_postings[j][0]:
            result.append(new_term_postings[j])
            i += 1
            j += 1
        elif intersection[i][0] < new_term_postings[j][0]:
            i += 1
        else:
            j += 1
    
    return result

def cosine_similarity(list1: list[int], list2: list[int]):
    return numpy.dot(list1, list2) / (numpy.linalg.norm(list1) * numpy.linalg.norm(list2))

def single_word_process(terms, iid, headings_iid, tagged_iid, total_pages):
    # assume i am getting the postings as input
    # all of them are dictionaries
    MIN_DOCS = 40
    terms.sort(key=lambda x: len(iid[x]))
    doc_scores = dict()
    multiplier = dict()
    for term in tagged_iid:
        for posting in tagged_iid[term]:
            doc_id = posting[0]
            multiplier[doc_id] = 1.1
    for term in headings_iid:
        for posting in headings_iid[term]:
            doc_id = posting[0]
            multiplier[doc_id] = 1.3

    for i in range(len(terms)):
        add_more = len(doc_scores) < 40
        for posting in iid[terms[i]]:
            doc_id = posting[0]
            freq = posting[1]
            if doc_id not in doc_scores and add_more:
                doc_scores[doc_id] = [0 for _ in range(len(terms))]
            doc_scores[doc_id][i] = (1 + math.log(freq))

    query_as_doc = Counter(terms)
    query_score = []
    for term in terms:
        query_score.append(tf_idf(term, -1, iid, total_pages, term_frequency=query_as_doc[term]))
    final_score_dict = dict()
    for doc_id in doc_scores:
        final_score_dict[doc_id] = cosine_similarity(doc_scores[doc_id], query_score) * (multiplier[doc_id] if doc_id in multiplier else 1)

    return positional_processing(terms, final_score_dict, iid)


def query_processing(q, terms: list[str | tuple], iid: dict[str, list[tuple[int]]], total_pages, headings_iid:dict[str, list[tuple[int]]], tagged_iid) -> list[int]:
    query_iid = {}
    headings = {}
    tagged = {}
    for token in terms:
        query_iid.update(iid.find_token(token))
        headings.update(headings_iid.find_token(token))
        tagged.update(tagged_iid.find_token(token))
    terms = sorted(terms, key=lambda x: len(query_iid[x]))
    intersection = None
    headings_intersection = None
    tagged_intersection = None
    doc_scores = defaultdict(list)
    for term in terms:
        if headings_intersection == None:
            headings_intersection = [(x[0], x[1]) for x in headings[term]]
        if tagged_intersection == None:
            tagged_intersection = [(x[0], x[1]) for x in tagged[term]]
        if intersection == None:
            intersection = [(x[0], x[1]) for x in query_iid[term]]
        else:
            new_term_postings = [(x[0], x[1]) for x in query_iid[term]]
            intersection = get_intersection(intersection, new_term_postings)
            headings_intersection = get_intersection(intersection,headings_intersection)
            tagged_intersection = get_intersection(intersection, tagged_intersection)
        for doc_id, frequency in intersection:
            if (doc_id, frequency) in headings_intersection:
                doc_scores[doc_id].append((1+ math.log(frequency))*1.3)
            elif (doc_id,frequency) in tagged_intersection:
                doc_scores[doc_id].append((1+ math.log(frequency))*1.1)
            else:
                doc_scores[doc_id].append(1+ math.log(frequency))
    
#     # calculate the cosine similarity
#     query_as_doc = Counter(terms)
#     query_score = []
#     for term in terms:
#         print(term)
#         query_score.append(tf_idf(term, -1, query_iid, total_pages, term_frequency=query_as_doc[term]))
#     pages_with_all_terms = [doc_id for doc_id in doc_scores if len(doc_scores[doc_id]) == len(query_score)]
#     ranking = sorted(pages_with_all_terms, 
#                      key= lambda doc_id: cosine_similarity(doc_scores[doc_id], query_score), reverse=True)
#     print(ranking)
#     q.put(ranking)




def ngrams_processing(q: multiprocessing.Queue, terms, ngrams_iid) -> dict[int, int]:
    local_iid = {}
    for token in terms:
        local_iid.update(ngrams_iid.find_token(token))
    terms = sorted(terms, key=lambda x: len(local_iid[x]))
    doc_scores = defaultdict(list)
    intersection = None
    for term in terms:
        if intersection == None:
            intersection = [(x[0], x[1]) for x in local_iid[term]]
        else:
            new_term_postings = [(x[0], x[1]) for x in local_iid[term]]
            intersection = get_intersection(intersection, new_term_postings)
    for doc_id, frequency in intersection:
        doc_scores[doc_id] = frequency * .05 + 1
    return doc_scores

def positional_processing(query, cand_docids: dict, local_iid):
    terms: list[(str, str, int)] = posify(query)
    for term in terms:
        first_posting = local_iid[term[0]]
        second_posting = local_iid[term[1]]
        i = 0
        j = 0
        while i < len(first_posting) and j < len(second_posting):
            if first_posting[i][0] == second_posting[i][0] and first_posting[i][0] in cand_docids:
                freq = positional_matching(first_posting[i], second_posting[i], term[2])
                cand_docids[first_posting[i][0]] *= freq * .05 + 1
                i += 1
                j += 1
            elif first_posting[i][0] < second_posting[i][0]:
                i += 1
            else:
                j += 1
    return cand_docids
        
def posify(query):
    pass



def positional_matching(list1: list[int], list2: list[int], target) -> set[int]:
    'Find how many integers in the list1 are a target number difference from list2'
    i = 2
    j = 2
    res = 0
    while i < len(list1) and j < len(list2):
        if list2[i] - list1[i] == target:
            i += 1
            j += 1
            res += 1
        elif list2[i] - list1[i] > target:
            i += 1
        else:
            j += 1    
    return res
