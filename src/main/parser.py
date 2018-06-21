#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from io import StringIO
from re import compile, sub, findall, search, escape, DOTALL, match
from time import time
from subprocess import call
from glob import glob
from itertools import zip_longest
from PIL import Image
from pdfminer.pdfinterp import PDFResourceManager, PDFPageInterpreter
from pdfminer.converter import PDFPageAggregator
from pdfminer.converter import TextConverter
from pdfminer.layout import LAParams
from pdfminer.layout import LTContainer
from pdfminer.layout import LTTextBox
from pdfminer.layout import LTTextLine
from pdfminer.layout import LTTextLineHorizontal
from pdfminer.layout import LTAnno
from pdfminer.layout import LTImage
from pdfminer.layout import LTFigure
from pdfminer.layout import LTTextBoxHorizontal
from pdfminer.layout import LTChar
from pdfminer.pdfpage import PDFPage

from difflib import get_close_matches, SequenceMatcher

from util.helper import Helper

class Parser(object):
	
	def __init__(self):
		self.src_root = os.getcwd()
		self.standard_paorg_detect_accuracy = 0.65
		self.acronym_paorg_detect_accuracy = 0.85
		self.__project_path = os.getcwd()
		self.__illegal_chars = compile(r"\d+")
		self.dec_contents_key = "ΠΕΡΙΕΧΟΜΕΝΑ\nΑΠΟΦΑΣΕΙΣ"
		self.decs_key = "ΑΠΟΦΑΣΕΙΣ"
		# Must be expanded (lots of variants)
		self.dec_prereq_keys = ["Εχοντας υπόψη:", "Έχοντας υπόψη:", "Έχοντας υπόψη:", "Έχοντας υπόψη του:", "Έχοντας υπ\' όψη:", 
							    "Έχοντας υπ\’ όψη:", "Αφού έλαβε υπόψη:", "Λαμβάνοντας υπόψη:"]
		self.dec_init_keys = ["αποφασίζουμε:", "αποφασίζουμε τα ακόλουθα:", "αποφασίζουμε τα εξής:",
							  "αποφασίζει:", "αποφασίζει τα ακόλουθα:", "αποφασίζει τα εξής:", "αποφασίζει ομόφωνα:",
							  "αποφασίζει ομόφωνα και εγκρίνει:", "αποφασίζει τα κάτωθι", "αποφασίζεται:", 
							  "με τα παρακάτω στοιχεία:"]
		self.dec_end_keys = {'start_group': ["Η απόφαση αυτή", "Ηαπόφαση αυτή", "Η απόφαση", "Η περίληψη αυτή", "ισχύει"],	
							 'finish_group': ["την δημοσίευση", "τη δημοσίευση", "τη δημοσίευσή", "να δημοσιευθεί", "να δημοσιευτεί", "να δημοσιευθούν",  "F\n"]}
		self.respa_keys = {'assignment_verbs':["Αναθέτουμε", "αναθέτουμε"], 
						   'assignment_types':["καθηκόντων", "αρμοδιοτήτων"]}

	# @TODO:
	# - Fine-tune section getters (see specific @TODOs)
	# - Manual annotation/extraction module of PAOrgs & RespAs, inputs: PAOrgs-assignment keys lists

	def get_dec_contents_from_txt(self, txt):
		txt = Helper.clean_up_for_dec_related_getter(txt)
		dec_contents = findall(r"{}(.+?){}".format(self.dec_contents_key, self.decs_key), txt, flags=DOTALL)
		if dec_contents:
			assert(len(dec_contents) == 1)
			dec_contents = dec_contents[0]
		return dec_contents
	
	# @TODO: Find a way to always properly separate dec_summaries from each other
	def get_dec_summaries_from_txt(self, txt, dec_contents):
		""" Must be fed 'dec_contents' as returned by get_dec_contents() """
		txt = Helper.clean_up_for_dec_related_getter(txt)
		if dec_contents:
			dec_summaries = findall(r"([Α-ΩΆ-Ώ].+?(?:(?![Β-ΔΖΘΚΜΝΞΠΡΤΦ-Ψβ-δζθκνμξπρτφ-ψ]\.\s?\n).)+?\.\s?\n)\d?\n?", dec_contents, flags=DOTALL)
			# Strip of redundant dots
			dec_summaries = [sub("\.{3,}", "", dec_sum) for dec_sum in dec_summaries]
			# Ignore possible "ΔΙΟΡΘΩΣΗ ΣΦΑΛΜΑΤΩΝ" section
			dec_summaries = [dec_sum for dec_sum in dec_summaries if 'Διόρθωση' not in dec_sum]
		else:
			# Will also contain number e.g. Αριθμ. ...
			dec_summaries = findall(r"{}\n\s*(.+?)\.\n\s*[Α-ΩΆ-Ώ()]".format(self.decs_key), txt, flags=DOTALL)
			assert(len(dec_summaries) == 1)
		return dec_summaries

	# Nums, meaning e.g. "Αριθμ." ...
	def get_dec_nums_from_txt(self, txt, dec_summaries):
		""" Must be fed 'dec_summaries' as returned by get_dec_summaries() """
		txt = Helper.clean_up_for_dec_related_getter(txt)
		dec_nums = []
		if dec_summaries:
			if len(dec_summaries) == 1:
				dec_nums = {1: [dec_num for dec_num in dec_summaries[0].split('\n') if 'ριθμ.' in dec_num][0]}
			elif len(dec_summaries) > 1:
				dec_idxs = []
				for idx in range(len(dec_summaries)):
					num_in_parenth = findall("\(({})\)\n?".format(idx + 1), txt)[0]
					dec_idxs.append(int(num_in_parenth))
				
				dec_nums = findall("\n\s*((?:(?:['A'|'Α']ριθμ\.)|(?:['A'|'Α']ριθ\.))[^\n]+)\n", txt)
				dec_nums = dict(zip_longest(dec_idxs, dec_nums))
		return dec_nums

	def get_dec_prereqs_from_txt(self, txt, dec_num):
		""" Must be fed 'dec_num', currently: len(dec_summaries) """
		txt = Helper.clean_up_for_dec_related_getter(txt)
		dec_prereqs = {}
		prereq_bodies = findall(r"(?:{})(.+?)(?:{})".format(Helper.get_special_regex_disjunction(self.dec_prereq_keys),
										   	 	   		    Helper.get_special_regex_disjunction(self.dec_init_keys)), 
										 			   	   	txt, flags=DOTALL)
		if prereq_bodies:
			if(len(prereq_bodies) >= dec_num):
				for dec_idx in range(len(prereq_bodies)):
					dec_prereqs[dec_idx + 1] = prereq_bodies[dec_idx]

			elif (len(prereq_bodies) < dec_num):
				# Just return detected ones as list (without index correspondence)
				dec_prereqs = prereq_bodies

		else: 
			if dec_num == 1:
				dec_prereqs = findall(r"\.\n[Α-ΩΆ-Ώ](.+?)(?:{})".format(Helper.get_special_regex_disjunction(self.dec_init_keys)), 
										   				 		    txt, flags=DOTALL)
			elif dec_num > 1:
			# For now 

				pass				

		return dec_prereqs

	def get_decisions_from_txt(self, txt, dec_num):
		""" Must be fed 'dec_num', currently: len(dec_summaries) """
		txt = Helper.clean_up_for_dec_related_getter(txt)
		dec_bodies = findall(r"(?:{})(.+?)(?:(?:(?:{}).+?(?:{}))|(?:{}))"\
								  .format(Helper.get_special_regex_disjunction(self.dec_init_keys),
								  		  Helper.get_special_regex_disjunction(self.dec_end_keys['start_group']),
								  		  Helper.get_special_regex_disjunction(self.dec_end_keys['finish_group']),
								  		  Helper.get_special_regex_disjunction(self.dec_prereq_keys)), 
								  		  txt, flags=DOTALL)
		
		# Try to get possible leftovers (exceptions)
		if(len(dec_bodies) < dec_num):
			# Fetch raw part from (remaining_dec_idx) to (remaining_dec_idx + 1)
			for remaining_dec_idx in range(len(dec_bodies), dec_num):
				leftover_dec_bodies = findall(r"(?:\n\({}\)\n).+?(?:\n\({}\)\n)"\
									  		  .format(remaining_dec_idx + 1, remaining_dec_idx + 2), 
									  	 	 txt, flags=DOTALL)

				dec_bodies += leftover_dec_bodies
		elif len(dec_bodies) >= dec_num:
			dec_bodies = dict(zip(range(1, dec_num + 1), dec_bodies))
	
		return dec_bodies

	# @TODO: 
	# 		1. Refine
	#		2. Make format of final result definite
	def get_dec_signees_from_txt(self, txt):
		# E.g. "Οι Υπουργοί", "Ο ΠΡΟΕΔΡΕΥΩΝ" etc.
		dec_signees_general_occup_pattern = "{year}\s*\n\s*{ordered_by}?((?:{gen_occupation}))\s*\n"\
											.format(year="\s\d{4}", 
										    		ordered_by= "(?:Με εντολή(?:[ ][Α-ΩΆ-Ώ][α-ωά-ώΑ-ΩΆ-Ώ]+)+\n)",
										    		gen_occupation="[Α-ΩΆ-Ώ][α-ωά-ώΑ-ΩΆ-Ώ]?(?:[ ][Α-ΩΆ-Ώ][α-ωά-ώΑ-ΩΆ-Ώ]+)+")
		regex_dec_signees_general_occup = compile(dec_signees_general_occup_pattern, flags=DOTALL)
		dec_signees_general_occup = findall(regex_dec_signees_general_occup, txt)

		# E.g. "ΧΑΡΑΛΑΜΠΟΣ ΧΡΥΣΑΝΘΑΚΗΣ"
		dec_signees = []
		if dec_signees_general_occup:
			for general_occup in dec_signees_general_occup:
				dec_signees_pattern = "\n\s*{general_occup}\s*\n\s*({signees})\n"\
									  .format(general_occup=general_occup,
											  signees="(?:[Α-ΩΆ-Ώκ−-][α-ωά-ώΑ-ΩΆ-ΏΪΫ\.,−/\-]*\s*)+")
				regex_dec_signees = compile(dec_signees_pattern, flags=DOTALL)
				dec_signees.append(findall(regex_dec_signees, txt))
		
		assert(len(dec_signees_general_occup) == len(dec_signees))
		return dict(zip(dec_signees_general_occup, dec_signees))

	def get_dec_location_and_date_from_txt(self, txt):
		regex_dec_location_and_date = Helper.get_dec_location_and_date_before_signees_regex()
		dec_location_and_dates = findall(regex_dec_location_and_date, txt)
		return dec_location_and_dates

	def get_paorgs_from_txt(self, txt, paorgs_list):
		""" Must be fed a pre-fetched 'paorgs_list' """
		txt = Helper.clean_up_for_paorgs_getter(txt)
		
		# Match possible PAOrg acronyms 	
		possible_paorg_acronyms_regex = compile('([Α-ΩΆ-Ώ](?=\.[Α-ΩΆ-Ώ])(?:\.[Α-ΩΆ-Ώ])+)') 
		possible_paorg_acronyms = findall(possible_paorg_acronyms_regex, txt)
		# print(possible_paorg_acronyms)
		
		# Match consecutive capitalized words possibly signifying PAOrgs
		possible_paorgs_regex = compile('([Α-ΩΆ-Ώ][α-ωά-ώΑ-ΩΆ-Ώ]+(?=\s[Α-ΩΆ-Ώ])(?:\s[Α-ΩΆ-Ώ][α-ωά-ώΑ-ΩΆ-Ώ]+)+)')
		possible_paorgs = findall(possible_paorgs_regex, txt)
		
		possible_paorgs = list(set(possible_paorg_acronyms + possible_paorgs))
		matching_paorgs = []
		for word in possible_paorgs:
			print(word)
			if word not in possible_paorg_acronyms:
				best_matches = get_close_matches(word.upper(), paorgs_list, cutoff=self.standard_paorg_detect_accuracy)
			else:
				best_matches = get_close_matches(word.upper(), paorgs_list, cutoff=self.acronym_paorg_detect_accuracy)
				best_matches += get_close_matches(word.upper().replace('.',''), paorgs_list, cutoff=self.acronym_paorg_detect_accuracy)
			
			if best_matches:
				matching_paorgs.append({word:best_matches})
		
		return matching_paorgs

	def get_respas_from_txt(self, txt):
		respas = []
		if txt:
			rough_respas = findall(r"\n(.+?(?:{assign_verb}).+?(?:{assign_type}).+?)\.\s*\n"\
								   .format(assign_verb=Helper.get_special_regex_disjunction(self.respa_keys['assignment_verbs']), 
								   		   assign_type=Helper.get_special_regex_disjunction(self.respa_keys['assignment_types'])), 
									txt, flags=DOTALL)
		return rough_respas

	def get_simple_pdf_text(self, file_name, txt_name):
		try:
			text = self.simple_pdf_to_text(file_name, txt_name)
		except OSError:
			raise

		return text

	def simple_pdf_to_text(self, file_name, txt_name):
		if not os.path.exists(file_name):
			raise OSError("'{}' does not exist!".format(file_name))
		
		if os.path.exists(txt_name):
			print("'{}' already exists! Fetching text anyway...".format(txt_name))
		else:
			rel_in =  escape(file_name)
			rel_out = escape(txt_name)
			
			# Convert
			cmd = 'pdf2txt.py {} > {}'.format(rel_in, rel_out)
			print("'{}' -> '{}':".format(file_name, txt_name), end="")
			call(cmd, shell=True)

		# Read .txt locally
		text = ''
		with open(txt_name) as out_file:
			text = out_file.read()

		cid_occurs = findall(r'\(cid:\d+\)', text)
		
		# Ignore cid occurences for now
		for cid in cid_occurs:
			text = text.replace(cid, '')
			# cid_int = int(''.join(filter(str.isdigit, cid)))
		
		# Overwrite .txt 
		with StringIO(text) as in_file, open(txt_name, 'w') as out_file:
			for line in in_file:
				if not line.strip(): continue # skip empty lines
				out_file.write(line)
		
		print("DONE.")

		# Read .txt locally again
		text = ''
		with open(txt_name) as out_file:
			text = out_file.read()

		return text