"""
Install script

modifications file: modifications.json, this structure (small example):

{
	"old":
	{
		"tech_tree":
		{
			"basicRocketry":
			{
				"title":"#autoLOC_501020 //#autoLOC_501020 = Basic Rocketry",
				"description":"#autoLOC_501023 //#autoLOC_501023 = How hard can Rocket Science be anyway?",
				"cost":5,
				"hideEmpty":"False",
				"nodeName":"node1_basicRocketry",
				"anyToUnlock":"False",#TODO: what does this do?
				"icon":"RDicon_rocketry-basic",
				"pos":"-2300,1200,0",
				"scale":"0.6",
				"parents":
				[
					{
						"parentID":"start",
						"lineFrom":"RIGHT",
						"lineTo":"LEFT"
					},
				],
			},

			#testNode is not present
		},
		"parts":
		{
			"noseCone":
			{
				"cfg_path":"Parts/Aero/aerodynamicNoseCone/aerodynamicNoseCone.cfg",
				"tech_id":"stability",
				#all other fields (e.g. title) ignored
			},
			"fairingSize1":
			{
				"cfg_path":"Parts/Aero/fairings/fairingSize1.cfg",
				"tech_id":"advConstruction",
				#all other fields (e.g. title) ignored
			},
		},
	},
	"new",
	{
		"tech_tree":
		{
			#basicRocketry node is not present
			"testNode":
			{
				exists:true,
				#id is populated based on the id provided 2 levels up from here
				
				"title":"Test Node",
				"description":"This is a Test R&D node",
				"cost":50,
				#hideEmpty is false except for nanolathing and experimental motors??? what does it do? for now we're going to populate ours as false always
				#nodeName is populated automatically with node<depth [distance in tree from start]>_id
				#anyToUnlock (what does this do????)
				"icon":"RDicon_test_node",
				#pos is calculated automatically
				#scale is always 0.6?
				"parents":
				[
					{
						"parentID":"engineering101",
						#from is always 'RIGHT'
						#to is always 'LEFT'
					},
					{
						"parentID":"basicRocketry"
					},
				],
			},
		},
		"parts":
		{
			"noseCone":
			{
				"cfg_path":"Parts/Aero/aerodynamicNoseCone/aerodynamicNoseCone.cfg",
				"tech_id":"stability",#unchanged
				#all other fields (e.g. title) ignored
			},
			"fairingSize1":
			{
				"cfg_path":"Parts/Aero/fairings/fairingSize1.cfg",
				"tech_id":"testNode",#changed
				#all other fields (e.g. title) ignored
			},
		}
	},
}

NOTE: the modifications file will generally only define 'new' OR 'old' but not both -- running this script with 'old' defined will revert, running it with 'new' defined will install

some notes on 'pos'

the tech tree is a directed acyclic graph. this means we can be fairly sure that there is at least one good way of drawing it where each layer (layer x is x hops from the 'root' (i.e. the tech node called 'start')) is in a big column. what that means is that we can reduce the difficulty (for the modder) of figuring out a good layout to a much simpler problem (simpler than specifing x/y coords for every damned node): give each node a rank (we'll tell them if they screw up) and just draw the tree in order of rank.
Here's what the syntax for that will look like:

<mods file>
{
"old"
... (this will preserve the original "pos" field along with everything else)

"new"
{
	"tech_tree"
	{
		"testNode"
		{
			"title": "Test Node",
			"description": "test... node.",
			"cost": 500,
			"icon": "RDicon_test-node",
			"parents":
			[
				{
					"parentID":"testParent1"
				},
				{
					"parentID":"testParent2"
				},
			],
			"ttm_rank":0,
			"ttm_layer":5
		}
		"testNode2"
		{
			"title": "Test Node",
			"description": "test... node.",
			"cost": 500,
			"icon": "RDicon_test-node",
			"parents":
			[
				{
					"parentID":"testParent2"
				},
				{
					"parentID":"testParent3"
				},
			],
			"ttm_rank":1,
			"ttm_layer":5
		}
	}

	"parts"
	...
},
"pos_strategy":"rank",#auto would run whatever algorithm this script says is best
}

and we'd see the whole 'ttm_rank' thing (ttm stands for tech-tree modify, btw) and print rank 0 at one end (probably the bottom), then rank 1, then rank 2, and so on.

the template would then also be populating layer for the modder so that they don't screw that part up (hopefully)
we'll also add a little flag to the top level of the mods file that says whether the user is using this strategy for tree layout
"""

import json
import argparse
import re
import time
import os
import warnings

# warnings.filterwarnings('error',category=SyntaxWarning)

MODIFIERS_PARENTS_LIST_KEY = "parents"
#TODO (eventually) support for non-squad tree data?
TECH_TREE_CFG_FILE_LOC_FROM_GAMEDATA_DIR = "/Squad/Resources/TechTree.cfg"

X_MIN = -2500
Y_MIN = 500
X_GAP = 200
Y_GAP = 60

clean_bracket_re = re.compile(r"\s*[{}]\s*")
dirty_bracket_re = re.compile(r"(.*)[{}](.*)")
whitespace_only_re = re.compile(r"^\s*$")
cfg_comment_re = re.compile(r"([^/]*)//(.*)")
comment_describes_autoLOC_re = re.compile(r"(.*)(title|description)\s*=\s*(?:.*//\s*(?:#?autoLOC_\S*\s*=)?\s*)?(.*)")
defn_re = re.compile(r"\s+(\w+)\s*=\s?(.*)")#capture group 1: identifier; group 2: definition
rd_node_re = re.compile(r"\s*RDNode")
par_begin_re = re.compile(r"\s*Parent")
defn_ident_is_id_re = re.compile(r"[Ii][Dd].*")
id_re = re.compile(r"\s*name\s*=\s*(\S+)")
tech_req_re = re.compile(r"\s*TechRequired\s*=\s*(\S+)")
partdef_begin_re = re.compile(r"(?:.{0,3}|\s*)PART")
open_brace_re = re.compile(r".*\{")
closed_brace_re = re.compile(r".*\}")
part_title_re = re.compile(r".*title\s*=\s*(?:.*//\s*(?:#?autoLOC_\S*\s*=)?\s*)?(.*)")

#whitelist this (only "PART" is allowed)
part_igdef_re = re.compile(r"\s*[A-Z]+\s*$")
def line_begins_ignored_defn(line):
	if partdef_begin_re.match(line) is not None:
		return False
	#add any other whitelisted matches here ^^^
	return part_igdef_re.match(line) is not None

tree_auto_fields = ['id',
					'hideEmpty',
					'nodeName',
					'anyToUnlock',
					'pos',
					'scale']
tree_parent_auto_fields = ['lineFrom',
						   'lineTo']

def parse_existing_tree_file(tree_path):
	flines = None
	with open(tree_path,'r') as f:
		flines = f.readlines()
		flines = [line[:-1] for line in flines]
		
	#preprocess the lines
	#delete the first line (it just says 'TechTree', or if it doesn't, we have the wrong file anyway)
	if('TechTree' != flines[0][-8:]):
		raise ValueError("File provided for the tech tree config ({}) is not a tech tree file (the first line is not 'TechTree' with no whitespace)".format(tree_path))
	else:
		flines.pop(0)
	#delete all the brackets (they're not necessary)
	flines_updated = []
	for line in flines:
		clean_match = clean_bracket_re.match(line)
		if clean_match is None:
			dirty_match = dirty_bracket_re.match(line)
			if dirty_match is not None:
				#either the beginning or the end of the line has non-whitespace
				#this line must be separated before the bracket can be deleted
				for group in range(1,2+1):
					#add all and only full and not whitespace-only groups
					if (dirty_match.group(group) is not None) and (whitespace_only_re.match(dirty_match.group(group)) is not None):
						flines_updated.append(dirty_match.group(group))
			else:
				#non bracket line
				flines_updated.append(line)
		else:
			#clean bracket line
			#do nothing
			pass
	flines = flines_updated
	#delete all the comments
	for i,line in enumerate(flines):
		comment_match =  cfg_comment_re.match(line)
		if comment_match is not None:
			autoloc_match = comment_describes_autoLOC_re.match(line)
			if autoloc_match is None:
				flines[i] = ""
			else:
				#drop all of the autoLOC references from here, but keep the description
				flines[i] = autoloc_match.group(1) + autoloc_match.group(2) + " = " + autoloc_match.group(3)
	flines_updated = []
	#clear whitespace
	for i,line in enumerate(flines):
		if whitespace_only_re.match(line) is None:
			flines_updated.append(line)
	flines = flines_updated

	
	
	out = {}
	current_dict_path = []#tells us where we're adding to in the out-dict
	
	searching_for_real_id = False#tells us whether we still haven't found this node's ID (we'll warn if we hit the next node before we do)
	'''
	temp_id_index = 0
	temp_id_prefix = "TEMPORARY_ID_{}_".format(time.time())#ensures this is unique
	def get_temp_id():
		r = temp_id_prefix + str(temp_id_index) #what the fuck. why is temp_id_index out of scope.
		temp_id_index += 1
		return r
	'''

	def get_temp_id():
		return "TEMPORARY_ID_{}".format(time.time())

	for line in flines:
		#rdnode defn begin
		rdnode_begin = rd_node_re.match(line) is not None
		#parent definition begin
		par_begin = par_begin_re.match(line) is not None
		#definition of variable
		def_match = defn_re.match(line)
		def_ident = None
		def_val = None
		if def_match is not None:
			def_ident = def_match.group(1)
			def_val = def_match.group(2)
		
		
		#process
		if rdnode_begin:
			#check if we got an ID for the last node
			if searching_for_real_id:
				#we didn't, warn the user
				warnings.warn("'id = <val>' definition was not found for an RDNode. Its ID will be {}".format(current_dict_path[0]), SyntaxWarning)
			#prepare to process the new rd-node
			#create a temp ID (we'll replace it when we learn the new ID, or throw a warning if we never do)
			current_dict_path = [get_temp_id()]
			out.update({current_dict_path[0]:{}})
			searching_for_real_id = True

		elif par_begin:
			#if this is the first parent, add 'parents' to the dict path and make a new entry
			#otherwise just make a new entry
			if 3 != len(current_dict_path):
				par_list_idx = -1
				out[current_dict_path[0]].update({MODIFIERS_PARENTS_LIST_KEY:[]})
				current_dict_path.append(MODIFIERS_PARENTS_LIST_KEY)
			else:
				par_list_idx = current_dict_path.pop(-1)#drop (and record) the parent list index
				
			out[current_dict_path[0]][current_dict_path[1]].append({})#the new parent object
			current_dict_path.append(par_list_idx + 1)#which has index <prev> + 1
			
		elif def_match is not None:
			
			#check if the ident is 'id'
			if defn_ident_is_id_re.match(def_ident) is not None:
				#we need to change the key that refers to this node
				#copy contents
				out[def_val] = out[current_dict_path[0]]
				#delete old stuff
				del out[current_dict_path[0]]
				#update the path
				current_dict_path[0] = def_val
				#unset the flag
				searching_for_real_id = False
			
			#otherwise, just add it in
			#different location if processing parents
			if 3 == len(current_dict_path):
				out[current_dict_path[0]][current_dict_path[1]][current_dict_path[2]].update({def_ident:def_val})
			else:
				out[current_dict_path[0]].update({def_ident:def_val})
	
	return out

def parse_existing_part_files(path_to_parts_dir,parts_dict=None):
	
	if parts_dict is None:
		parts_dict = {}#consists of <path>:{ "old_tech_id":<id>, "new_tech_id":"" }
	
	ignore_files = {'VariantThemes.cfg'}
	filetype_filter = '.cfg'
	
	#first, find every .cfg file under this directory (dropping anything from the ignore list)
	flist = set()
	for dirpath,dirnames,filenames in os.walk(path_to_parts_dir):
		flist = flist.union({dirpath + '/' + fname for fname in filenames if (fname[-4:] == filetype_filter) and (fname not in ignore_files)})
	
	
	
	for fpath in flist:
		flines = []
		with open(fpath,'r',errors='replace') as f:
			flines = f.readlines()
			flines = [line[:-1] for line in flines]
		
		flines_re_out = []
		re_out_file = False
		line_id = 0
		while line_id < len(flines):
			#start by looking for a part-definition beginning
			partdef_found = False
			part_begin_loc = None
			for line in flines[line_id:]:
				line_id += 1
				flines_re_out.append(line)
				if partdef_begin_re.match(line) is not None:
					partdef_found = True
					part_begin_loc = line_id-1
					break
			
			if not partdef_found:
				break
			
			#look for the id and the tech-req (order doesn't matter)
			id = None
			treq = None
			#optional: look for a part title match (can help with templating)
			title = None

			ignored_def_brace_level = 0  #used to ignore certain definitions
			watch_for_ignore_open_brace = False
			
			for line in flines[line_id:]:
				line_id += 1
				flines_re_out.append(line)

				#ignored sections
				if (ignored_def_brace_level > 0) or (watch_for_ignore_open_brace):
					#look for an open brace
					if open_brace_re.match(line) is not None:
						if watch_for_ignore_open_brace:
							#we found it, stop looking
							watch_for_ignore_open_brace = False
						ignored_def_brace_level += 1
					#look for a close brace
					elif closed_brace_re.match(line) is not None:
						ignored_def_brace_level -= 1

					continue#don't do anything to process this part (it's either closed brace [do nothing anyway] or within a module definition [needs to  be ignored])
				#check if there's a new ignored definition starting
				elif line_begins_ignored_defn(line):
					ignored_def_brace_level = 0
					watch_for_ignore_open_brace = True#need this because the open brace should  be on the next line (or later, if the dev decides to put blank lines between us  and it *RAGE*)
					continue

				#new part definition
				if partdef_begin_re.match(line) is not None:
					line_id -= 1
					break
				
				idmatch = id_re.match(line)
				treqmatch = tech_req_re.match(line)
				titlematch = part_title_re.match(line)
				if idmatch is not None:
					id = idmatch.group(1)
					#reorder if they were out of order
					if(treq is not None):
						warnings.warn("config file {} contained a part (part def begins on line {}) with tech-req defined BEFORE part id (field: name). Reordering in the file".format(fpath,part_begin_loc), SyntaxWarning)
						re_out_file = True
						#delete the id line from the new lines
						idline = flines_re_out.pop(-1)
						#add it in at the beginning
						flines_re_out.insert(part_begin_loc+2,idline)
				if treqmatch is not None:
					treq = treqmatch.group(1)
				if titlematch is not None:
					title = titlematch.group(1)
				
			if (id is None) or (treq is None):
				warnings.warn("config file {} contained a part (part def begins on line {}, error found on line {})  that failed to define both tech-requirement and part id (field: name). Ignoring this part (most likely: part does not have a tech requirement [e.g. flags or eva suits])".format(fpath,part_begin_loc,line_id-1), SyntaxWarning)
			else:
				id_attach_val = 0
				new_id = id
				while new_id in parts_dict:
					#attach an index to make it unique
					warnings.warn("more than one part has name {}".format(new_id), SyntaxWarning)
					new_id = id + str(id_attach_val)
					id_attach_val += 1
				
				id = new_id
				if title is not None:
					parts_dict.update({id:{
						'cfg_path':fpath,
						'tech_id':treq,
						'title':title
						}})
				else:
					#warn that we didn't find the title for this one
					warnings.warn("no title field was found for part with id {} (file {})".format(id,fpath))
					parts_dict.update({id: {
						'cfg_path': fpath,
						'tech_id': treq
					}})
		
		if re_out_file:
			#something was wrong in the file, fix it and re-output the file
			with open(fpath,'w',errors='replace') as f:
				f.writelines([line + '\n' for line in flines_re_out])
	
	return parts_dict

def get_modifications(mod_file):
	return json.load(open(mod_file,'r'))

def generate_nodes_depth(tech_tree):
	#how far is each node from 'start'
	return {node:get_node_depth(tech_tree,node) for node in tech_tree}

def auto_generate_nodes_ypos(tech_tree,next_yv_by_depth,ymax,depth_hist,node_depths):
	#make a version of the tree that's "forwards" (nodes map to lists of their children)
	forward_tree = {node: [] for node in tech_tree}
	for node in tech_tree:
		if 'parents' not in tech_tree[node]:
			continue
		for par in tech_tree[node]['parents']:
			forward_tree[par['parentID']].append(node)
	#now we do a depth-first search through the tree. the first path we traverse goes along the top edge (lowest available y-values), then so on from there
	stack = ['start']
	tech_tree['start']['pos'][1] = next_yv_by_depth[0]  #this is normally added on by the parent, but start has no parent, so do it now
	next_yv_by_depth[0] += ymax/depth_hist[0]  #this shouldn't be necessary -- only 'start' should be at depth 0
	#we'll use the y-value in tech_tree[node]['pos'] as a 'seen' value
	while len(stack) > 0:
		cur = stack.pop(-1)  #take from end

		#y-value is already assigned, just add children to the stack
		for ch in forward_tree[cur]:
			#check if seen
			if tech_tree[ch]['pos'][1] is not None:
				#seen
				continue
			else:
				#not seen, give y-pos and add to stack
				stack.append(ch)
				tech_tree[ch]['pos'][1] = next_yv_by_depth[node_depths[ch]]
				#move the yv for this depth to the next position
				next_yv_by_depth[node_depths[ch]] += ymax/depth_hist[node_depths[ch]]

def generate_nodes_ypos_rank(tech_tree,next_yv_by_depth,ymax,depth_hist,node_depths):
	#use the rank information provided to populate the y-positions
	#list of dicts (one per layer) mapping rank to node name
	ranks = [{} for _ in range(len(depth_hist))]
	#first, verify that the rank info is valid
	for node in tech_tree:
		#make sure the layer in the file is correct (not a dealbreaker, since it's only there to help the modder, but they do need to know)
		if 'ttm_layer' not in tech_tree[node]:
			warnings.warn("rank y-position mode was requested, but node {} does not define a ttm layer".format(node), SyntaxWarning)
		elif int(tech_tree[node]['ttm_layer']) != node_depths[node]:
			warnings.warn("rank y-position mode was requested, but node {} lists {} as its layer;"
						  " calculated layer for this node is {}"
						  " (I'm going to ignore the layer defined in the mod file and use the calculated one instead,"
						  " but your ttm_rank MAY NOT BE WHAT YOU THINK IT IS)"
						  .format(node,
								  tech_tree[node]['ttm_layer'],
								  node_depths[node]),
						  SyntaxWarning)

		#make sure we have a ttm_tank and that it is unique (doesn't matter if they're all in a row, or even if they're like nonnegative, just need them to be in *an* order)
		if 'ttm_rank' not in tech_tree[node]:
			raise ValueError("rank y-position mode was requested, but node {} does not provide a rank".format(node))
		elif int(tech_tree[node]['ttm_rank']) in ranks[node_depths[node]]:
			raise ValueError("node {} (layer {}) lists {} as its rank,"
							 " but another node in this layer ({}) also listed that as its rank (not unique rank)"
							 .format(node,
									 node_depths[node],
									 tech_tree[node]['ttm_rank'],
									 ranks[node_depths[node]][int(tech_tree[node]['ttm_rank'])]
									 ))
		else:
			ranks[node_depths[node]].update({int(tech_tree[node]['ttm_rank']) : node})

	#everything is verified, cleared to proceed
	#sort the nodes in each layer according to their rank (ascending or descending doesn't really matter)
	#flip the ranks dicts (node IDs map to their rank)
	ranks_flipped = [{d[k]:k for k in d} for d in ranks]
	layers_sorted_by_rank = [sorted(d.keys(),key=lambda x: d[x]) for d in ranks_flipped]

	#now just go through layer-by-layer and assign yvalues as we go
	for l in range(0,len(depth_hist)):
		for node in layers_sorted_by_rank[l]:
			tech_tree[node]['pos'][1] = next_yv_by_depth[l]
			#move the yv for this depth to the next position
			next_yv_by_depth[l] += ymax/depth_hist[l]
	#modifications done in place, so we're done
	pass

def generate_nodes_pos(tech_tree,node_depths=None):
	#TODO improve the loooks of this layout algorithm
	if node_depths is None:
		node_depths = generate_nodes_depth(tech_tree)

	#assign x-pos (start = X_MIN, then each node goes by its depth)
	for node in tech_tree:
		tech_tree[node].update({'pos':[X_MIN + (X_GAP * node_depths[node]), None, 0]})

	#create a histogram of node depths
	depth_hist = {i:0 for i in range(max(node_depths.values())+1)}
	for node in node_depths:
		depth_hist[node_depths[node]] += 1

	#the widest (y is width here) part will be perfectly dense (implicitly)
	num_in_widest_depth = max(depth_hist.values())
	ymax = Y_MIN + (Y_GAP * num_in_widest_depth)
	next_yv_by_depth = {d: Y_MIN for d in range(num_in_widest_depth)}

	#determine what y-position strategy to use
	if ('pos_strategy' not in tech_tree) or ('auto' == tech_tree['pos_strategy']):
		#do the standard one
		auto_generate_nodes_ypos(tech_tree,next_yv_by_depth,ymax,depth_hist,node_depths)
	elif 'rank' == tech_tree['pos_strategy']:
		generate_nodes_ypos_rank(tech_tree,next_yv_by_depth,ymax,depth_hist,node_depths)

	#all of the modifications were done in-place, so we are done
	pass
	
def auto_populate_missing_fields(tree_mods):
	#only touches certain fields:
	#	id
	#	hideEmpty
	#	nodeName
	#	anyToUnlock
	#	pos
	#	scale
	#	<parent>
	#		lineFrom
	#		lineTo
	#and even then only if the user didn't already populate them

	for tech_id in tree_mods:
		#populate id
		if 'id' not in tree_mods[tech_id]:
			tree_mods[tech_id].update({'id':tech_id})
		#hideEmpty
		if 'hideEmpty' not in tree_mods[tech_id]:
			tree_mods[tech_id].update({'hideEmpty':'True'})
		#anyToUnlock
		if 'anyToUnlock' not in tree_mods[tech_id]:
			tree_mods[tech_id].update({'anyToUnlock':'True'})#TODO wtf is this
		#scale
		if 'scale' not in tree_mods[tech_id]:
			tree_mods[tech_id].update({'scale':'0.6'})
		
		#parent info
		if MODIFIERS_PARENTS_LIST_KEY in tree_mods[tech_id]:
			for i in range(len(tree_mods[tech_id][MODIFIERS_PARENTS_LIST_KEY])):
				if 'lineFrom' not in tree_mods[tech_id][MODIFIERS_PARENTS_LIST_KEY][i]:
					tree_mods[tech_id][MODIFIERS_PARENTS_LIST_KEY][i].update({'lineFrom':'RIGHT'})
				if 'lineTo' not in tree_mods[tech_id][MODIFIERS_PARENTS_LIST_KEY][i]:
					tree_mods[tech_id][MODIFIERS_PARENTS_LIST_KEY][i].update({'lineTo':'LEFT'})

	#do pos and nodeName (depth) outside of the main loop
	node_depths = generate_nodes_depth(tree_mods)
	#nodeName
	#node<depth>_<id>
	for node in node_depths:
		tree_mods[node].update({'nodeName': 'node{}_{}'.format(node_depths[node],node)})
	#pos
	generate_nodes_pos(tree_mods,node_depths=node_depths)
	#done

def output_modifications(mods,mod_file):
	json.dump(mods,open(mod_file,'w'),indent='\t')
	
def apply_tree_modifications(tree_mods,tree_path):
	with open(tree_path,'w') as f:
		f.write('TechTree\n')
		f.write('{\n')
		
		for rdnode in tree_mods:
			f.write('\tRDNode\n')
			f.write('\t{\n')
			for field in tree_mods[rdnode]:
				#parents section handled separately
				if MODIFIERS_PARENTS_LIST_KEY == field:
					continue#parents should come last
				else:
					if ('pos' == field) and (str != type(field)):
						f.write('\t\t{} = {},{},{}\n'.format(field,*tree_mods[rdnode][field]))
					else:
						f.write('\t\t{} = {}\n'.format(field,tree_mods[rdnode][field]))
			if MODIFIERS_PARENTS_LIST_KEY in tree_mods[rdnode]:
				for par in tree_mods[rdnode][MODIFIERS_PARENTS_LIST_KEY]:
					f.write('\t\tParent\n')
					f.write('\t\t{\n')
					for parfield in par:
						f.write('\t\t\t{} = {}\n'.format(parfield,par[parfield]))
					f.write('\t\t}\n')
			f.write('\t}\n')
		
		f.write('}\n')
		
def apply_part_modifications(part_mods):
	for part_id in part_mods:
		path = part_mods[part_id]['cfg_path']
		treq = part_mods[part_id]['tech_id']
		
		flines = []
		with open(path,'r',errors='replace') as f:
			flines = f.readlines()
			flines = [line[:-1] for line in flines]
		
		#look for the 'name' field that matches
		name_fd_idx = None
		for i,line in enumerate(flines):
			if id_re.match(line) is not None:
				name_fd_idx = i
				break
		
		if name_fd_idx is None:
			raise ValueError("part ID {} not found in file {}".format(part_id,path))
		#look for the NEXT 'TechRequired' field
		treq_idx = None
		for i,line in enumerate(flines[name_fd_idx:]):
			if tech_req_re.match(line) is not None:
				treq_idx = i + name_fd_idx
				break
		
		#change the line
		flines[treq_idx] = "\tTechRequired = {}".format(treq)
		
		#output the file again
		with open(path,'w',errors='replace') as f:
			f.writelines([l + '\n' for l in  flines])

def get_node_depth(tech_tree,node):
	if('parents' not in tech_tree[node]):
		return 0

	return min([get_node_depth(tech_tree,par['parentID']) for par in tech_tree[node]['parents']]) + 1

if __name__ == '__main__':
	#main stuff
	
	parser = argparse.ArgumentParser(description="KSP tech tree modification install/uninstall/template creation")
	
	parser.add_argument('kspdir',type=str,help='KSP top level directory (this is the directory that contains the Launcher.exe executable and the GameData directory)')
	parser.add_argument('action',type=str,choices=['install','uninstall','template'],default='template',help='What do you want this program to do? (note: "template" will create a template of all of the parts in your game directory and the existing tech tree in the format this program expects)')
	parser.add_argument('modfile',type=str,help='Location of the file which contains (or will contain, in the case of template creation) the modifications to make to the tech tree. NOTE: expected file type/format: json')
	
	args = parser.parse_args()
	
	ksp_dir = args.kspdir
	game_data_dir = ksp_dir + '/GameData'
	action = args.action
	mod_file = args.modfile

	#verify inputs
	
	#make sure kspdir exists and does contain a subdirectory called GameData
	if not os.path.isdir(ksp_dir):
		raise ValueError("{} -- directory not found".format(ksp_dir))
	if not os.path.isdir(game_data_dir):
		raise ValueError("{} is not a valid KSP top level directory (GameData subdirectory does not exist)".format(ksp_dir))
		
	#argparse verifies action for us
	
	#check if the modfile exists
	if not os.path.isfile(mod_file):
		#it doesn't -- this is a problem in all types except template
		if 'template' != action:
			raise ValueError("{} -- file not found. Only template mode may fail to specify an existing file")
	#warn if the file the user gave doesn't end in '.json'
	if '.json' != mod_file[-5:]:
		warnings.warn("mod file path provided does not use the '.json' suffix -- the data stored in this file is in json format", SyntaxWarning)
	#trying to load the json in get_modifications will throw an error if it isn't syntactically correct, so no need to do so here
	
	#load/parse the existing tech tree
	current_tech_tree = parse_existing_tree_file(game_data_dir + TECH_TREE_CFG_FILE_LOC_FROM_GAMEDATA_DIR)
	#load/parse the existing parts
	#	find all of the 'Parts' directories
	pdirs = {dirpath for dirpath,_,_ in os.walk(game_data_dir) if '\\Parts' == dirpath[-6:]}
	#	parse all of the parts from these directories
	current_parts = {}
	for pdir in pdirs:
		current_parts = parse_existing_part_files(pdir, parts_dict = current_parts)
	
	#template creation
	if 'template' == action:
		#don't load the json from the file given
		#throw away any fields which we would auto-populate anyway (at best they confuse the user)
		#precompute node depths
		node_depths = generate_nodes_depth(current_tech_tree)
		new_tech_tree = {}
		for tech in current_tech_tree:
			new_tech_tree.update({tech:{field:current_tech_tree[tech][field] for field in current_tech_tree[tech] if (field not in tree_auto_fields) and ('parents' != field)}})
			#add in fields for ttm_layer (calculated) and ttm_rank (blank
			new_tech_tree[tech].update({'ttm_layer':node_depths[tech],
										'ttm_rank':"TODO"})
			if 'parents' in current_tech_tree[tech]:
				new_tech_tree[tech].update({'parents':[
					{field:current_tech_tree[tech]['parents'][i][field] for field in current_tech_tree[tech]['parents'][i] if field not in tree_parent_auto_fields}
					for i in range(len(current_tech_tree[tech]['parents'])) ]})

		current_tech_tree = new_tech_tree

		#format the dict we're going to throw into the mod file
		modf_data = {'pos_strategy':'rank',
					 'old':{'tech_tree':{},'parts':{}},
					 'new':{'tech_tree':{},'parts':{}}}
		#put the stuff we just read into 'new'
		modf_data['new']['tech_tree'] = current_tech_tree
		modf_data['new']['parts'] = current_parts

		#output the data and exit normally
		output_modifications(modf_data,mod_file)
		exit(0)
	else:
		#load in the json
		all_modf_data = get_modifications(mod_file)
		#installation
		if 'install' == action:
			#auto populate missing stuff from the file
			auto_populate_missing_fields(all_modf_data['new']['tech_tree'])
			#format the old modfile data
			all_modf_data.update({'old':{'tech_tree':current_tech_tree, 'parts':current_parts}})
			# exit(1)
			#push the changes to the json file
			output_modifications(all_modf_data,mod_file)
			#finally, do the install itself
			apply_tree_modifications(all_modf_data['new']['tech_tree'], game_data_dir + TECH_TREE_CFG_FILE_LOC_FROM_GAMEDATA_DIR)
			apply_part_modifications(all_modf_data['new']['parts'])
			#done, exit normally
			exit(0)
		#uninstallation (revert based on file)
		elif 'uninstall' == action:
			#works just like install, but we populate the 'old' values, not the 'new' ones
			#just do the (un)install itself
			apply_tree_modifications(all_modf_data['old']['tech_tree'],
									 game_data_dir+TECH_TREE_CFG_FILE_LOC_FROM_GAMEDATA_DIR)
			apply_part_modifications(all_modf_data['old']['parts'])
			#done, exit normally
			exit(0)