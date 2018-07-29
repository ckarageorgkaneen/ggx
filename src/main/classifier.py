from pandas import read_csv
from sklearn.model_selection import train_test_split
from sklearn import svm
from sklearn.model_selection import KFold
from sklearn.model_selection import cross_val_score
from sklearn.tree import DecisionTreeClassifier
from numpy import mean
from math import sqrt
from util.helper import Helper
import main.analyzer
from collections import OrderedDict, defaultdict

class RespAClassifier(object):
	
	def __init__(self, training_data_csv_file):
		self.training_data_csv_file = training_data_csv_file
		self.csv_column_names = ['A','B','C','D','E','F','G','H','I','RESPA']
		self.features = ['A','B', 'C','D','E','F','G','H','I']
		self.target_var = 'RESPA'
		self.df = read_csv(self.training_data_csv_file, sep=',', skiprows=1, names=self.csv_column_names)
		self.X = self.df[self.features]
		self.y = self.df[self.target_var]
		self.specialy = self.df[[self.target_var]]
		self.trained_model = self.train()
		
class IssueOrArticleRespAClassifier(RespAClassifier):

	# GG Issue & Article classifier
	# Predicts whether or not 'issue' contains RespA
	def train(self):
		return svm.SVC(kernel='linear', C=1).fit(self.X, self.y)

	def fit(self, txt, is_respa):
		txt_analysis_feature_vector = main.analyzer.Analyzer().get_n_gram_analysis_data_vectors([txt])
		Helper.append_rows_into_csv(txt_analysis_feature_vector + [is_respa], self.training_data_csv_file)
		# Update instance data
		self.__init__(self.training_data_csv_file)

	def cross_validate(self, test_size):
		X_train, X_test, y_train, y_test = train_test_split(self.X, self.y, test_size=test_size)
		clf = svm.SVC(kernel='linear', C=1).fit(X_train, y_train)
		
		return clf.score(X_test, y_test)

	def KFold_cross_validate(self):
		kf = KFold(n_splits=10)
		kf.get_n_splits(self.X)
		# print(kf)  
		kf = KFold(n_splits=10)
		clf_tree=DecisionTreeClassifier()
		scores = cross_val_score(clf_tree, self.X, self.specialy, cv=kf)
		avg_score = mean(scores)
		
		return avg_score

	# GG Issue & Article classifier
	# Predicts whether or not 'issue' contains RespA
	def has_respas(self, data_vector):
		return self.trained_model.predict([data_vector])

class ParagraphRespAClassifier(object):
	
	def __init__(self, training_data_files = None):
		if training_data_files is not None:
			self.training_data_files = training_data_files
			self.training_data = OrderedDict() 
			self.load_train_data('non_respa')
			self.load_train_data('respa')

		self.unit_keywords = ["ΤΜΗΜΑ", "ΓΡΑΦΕΙ", "ΔΙΕΥΘΥΝΣ", "ΥΠΗΡΕΣΙ", "ΣΥΜΒΟΥΛΙ", 'ΓΡΑΜΜΑΤΕ', "ΥΠΟΥΡΓ",
							  "ΕΙΔΙΚΟΣ ΛΟΓΑΡΙΑΣΜΟΣ"]
		self.responsibility_keyword_trios = [("ΑΡΜΟΔ", "ΓΙΑ", ":"),  ("ΑΡΜΟΔΙΟΤ", "ΕΧΕΙ", ":"), ("ΑΡΜΟΔΙΟΤ", "ΕΞΗΣ", ":"), 
										("ΑΡΜΟΔΙΟΤ", "ΕΙΝΑΙ", ":"), ("ΑΡΜΟΔΙΟΤ", "ΑΚΟΛΟΥΘ", ":"), ("ΑΡΜΟΔΙΟΤ", "ΜΕΤΑΞΥ", ":")]
														                         
	def load_train_data(self, tag):
		self.training_data[tag] = Helper.load_pickle_file(self.training_data_files[tag])

	def write_train_data(self, tag):
		Helper.write_to_pickle_file(self.training_data[tag], self.training_data_files[tag])

	def fit(self, paragraph, is_respa):
		words = Helper.get_clean_words(paragraph)[:20]
		word_bigrams = Helper.get_word_n_grams(words, 2)
		word_unigrams = Helper.get_word_n_grams(words, 1)

		appropriate_key = list(self.training_data)[is_respa]
		temp_unigram_dict = defaultdict(int, self.training_data[appropriate_key]['unigrams'])
		temp_bigram_dict = defaultdict(int, self.training_data[appropriate_key]['bigrams'])
		
		# Fit into training data
		for unigram in word_unigrams:
			temp_unigram_dict[unigram[0]] += 1
		for bigram in word_bigrams:
			temp_bigram_dict[(bigram[0], bigram[1])] += 1
		
		# Update instance data
		self.training_data[appropriate_key]['unigrams'].update(dict(temp_unigram_dict))
		self.training_data[appropriate_key]['bigrams'].update(dict(temp_bigram_dict))
		# And rewrite pickle file
		self.write_train_data(appropriate_key)

	def has_respas(self, paragraph):
		words = Helper.get_clean_words(paragraph)[:20]
		word_bigrams = Helper.get_word_n_grams(words, 2)
		word_unigrams = Helper.get_word_n_grams(words, 1)

		paragraph_bigram_dict = {(bigram[0], bigram[1]):1 for bigram in word_bigrams}
		paragraph_unigram_dict = {(unigram[0]):1 for unigram in word_unigrams}

		unigram_pos_cosine = self.cosine_similarity(paragraph_unigram_dict, self.training_data['respa']['unigrams'])
		unigram_neg_cosine = self.cosine_similarity(paragraph_unigram_dict, self.training_data['non_respa']['unigrams'])

		bigram_pos_cosine = self.cosine_similarity(paragraph_bigram_dict, self.training_data['respa']['bigrams'])
		bigram_neg_cosine = self.cosine_similarity(paragraph_bigram_dict, self.training_data['non_respa']['bigrams'])

		return (unigram_pos_cosine > unigram_neg_cosine), (bigram_pos_cosine > bigram_neg_cosine)

	def custom_has_respas(self, paragraph):
		words = Helper.get_clean_words(paragraph)[:20]
		word_bigrams = Helper.get_word_n_grams(words, 2)
		word_unigrams = Helper.get_word_n_grams(words, 1)
		paragraph_bigram_dict = {(bigram[0], bigram[1]):1 for bigram in word_bigrams}
		paragraph_unigram_dict = {(unigram[0]):1 for unigram in word_unigrams}
		
		unigram_pos_cosine, unigram_neg_cosine = 0, 0
		if paragraph_unigram_dict:
			unigram_pos_cosine = self.cosine_similarity(paragraph_unigram_dict, self.training_data['respa']['unigrams'])
			unigram_neg_cosine = self.cosine_similarity(paragraph_unigram_dict, self.training_data['non_respa']['unigrams'])

		bigram_pos_cosine, bigram_neg_cosine = 0, 0
		if paragraph_bigram_dict:
			bigram_pos_cosine = self.cosine_similarity(paragraph_bigram_dict, self.training_data['respa']['bigrams'])
			bigram_neg_cosine = self.cosine_similarity(paragraph_bigram_dict, self.training_data['non_respa']['bigrams'])

		weighted_pos_cosine = 0.9*bigram_pos_cosine + 0.1*unigram_pos_cosine
		weighted_neg_cosine = 0.9*bigram_neg_cosine + 0.1*unigram_neg_cosine

		return [paragraph, paragraph_unigram_dict, paragraph_bigram_dict, 
				(unigram_pos_cosine > unigram_neg_cosine), (bigram_pos_cosine > bigram_neg_cosine),
				(weighted_pos_cosine > weighted_neg_cosine)]

	def has_units(self, paragraph):
		paragraph = Helper.deintonate_txt(paragraph)
		paragraph = paragraph.upper()
		return any(unit_kw in paragraph
				   for unit_kw in self.unit_keywords)

	def has_only_units(self, paragraph):
		paragraph = Helper.deintonate_txt(paragraph)
		paragraph = paragraph.upper()
		return any((((unit_kw in paragraph) and\
					 (resp_kw_trio[0] not in paragraph) and\
					 (resp_kw_trio[1] not in paragraph) and\
					 (resp_kw_trio[2] not in paragraph)))
				    for unit_kw in self.unit_keywords
				    for resp_kw_trio in self.responsibility_keyword_trios)


	def has_units_and_respas(self, paragraph):
		paragraph = Helper.deintonate_txt(paragraph)
		paragraph = paragraph.upper()
		return any((((unit_kw in paragraph) and\
					 (resp_kw_trio[0] in paragraph) and\
					 (resp_kw_trio[1] in paragraph) and\
					 (resp_kw_trio[2] not in paragraph)))
				    for unit_kw in self.unit_keywords
				    for resp_kw_trio in self.responsibility_keyword_trios)

	def has_units_followed_by_respas(self, paragraph):
		paragraph = Helper.deintonate_txt(paragraph)
		paragraph = paragraph.upper()
		return any((((unit_kw in paragraph) and\
					 (resp_kw_trio[0] in paragraph) and\
				 	 (resp_kw_trio[1] in paragraph) and\
				 	 (resp_kw_trio[2] in paragraph)))
				    for unit_kw in self.unit_keywords
				    for resp_kw_trio in self.responsibility_keyword_trios)

	def cosine_similarity(self, dict_1, dict_2):
		numer = 0
		den_a = 0
		
		for key_1, val_1 in dict_1.items():
			numer += val_1 * dict_2.get(key_1, 0.0)
			den_a += val_1 * val_1
		den_b = 0
		
		for val_2 in dict_2.values():
			den_b += val_2 * val_2
		
		return numer/sqrt(den_a * den_b)
		 
   