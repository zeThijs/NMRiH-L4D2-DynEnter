from pyparsing import *
import sys
import os
import re


#TODO: save cordon information for later vscript use. 

cfg_skip_named_ents  = True #especially important to skip named entities when they have a movechild. dunno how to efficiently search if entity has movechild in entdata yet so, for now just skip named ents
#cfg_skip_infodecal  = True
cordonprefix    = "DynEnter_"

dynsp_cordons = []      #result element example:['outside', ['(-4596 -7322 -834)', '(-408 2192 4620.05)', entitycount]
cordonstrings = []


classnames = [
    "prop_physics",
    "prop_physics_override",
    "prop_dynamic",
    "prop_dynamic_override",
    "env_sprite",
    "keyframe_rope",
    "infodecal"
]

entfound_count = [0] * len(classnames) #store results based on classnames indexes

must_precache_mat = [] #If not precached before create, entities using these assets fail to load.

#find cordons with name DynEnter_*, put name, box in list 


#during analyzation of entities, move found entities in cordon groups. If not within cordon, skip entity

#for proper execution, install this in nmrih/bin/dynamicspawns


def main(filename):
    print("Starting precompile DynEnter step.")

    filepath = os.path.dirname(filename)
    basenamefull = os.path.basename(filename)
    basename = os.path.basename(filename).split('.')[0].split('_')[1]
    pythonscriptpath = get_script_path()
    vmf_outpath = pythonscriptpath + '/vmfoutput'
    vmf_out = vmf_outpath + '/' + basenamefull
    
    nmrihpath = os.path.dirname(os.path.dirname(pythonscriptpath))
    vscriptpath = nmrihpath + "/nmrih/scripts/vscripts" + '/DynEnter/'
    vscriptout_p = nmrihpath + "/nmrih/scripts/vscripts" + '/DynEnter/' + basename
    vscriptout_relativep = 'DynEnter/' + basename
  
    
    #create vscript output dir, if not exist
    if not os.path.isdir(vscriptpath): 
        os.mkdir(vscriptpath)
        
    #create vscript output dir, if not exist
    if not os.path.isdir(vscriptout_p): 
        os.mkdir(vscriptout_p)
    
    #create map output dir, if not exist
    if not os.path.isdir(vmf_outpath): 
        os.mkdir(vmf_outpath)

    print("Finish generating output directories")
    
    #copy input vmf into string variable to remove dynamic-spawnified entities.    
    infile = open(filename, 'r')
    vmfstr = infile.read()
    infile.close()
    
    
    
    LBRACE, RBRACE = map(Suppress, '{}')
    key = dblQuotedString | Word(printables, excludeChars='{}/')
    value = Forward()
    node = Group(key + value)
    dblQuotedString.setParseAction(removeQuotes)
    section = Group(LBRACE + ZeroOrMore(node) + RBRACE)
    value << (key | section)
    results = OneOrMore(node).parseFile(filename).asList()
    
    outstr = ''
    count=0
    
    print("Analyzing cordon areas..")

    #get cordons
    for entry in results:
        if entry[0] == 'cordons':
            if not index_cordons(entry[1]):
                print("Could not find correctly named cordons." )
                print("To use dynamic entities: prefix your cordon with \'" + cordonprefix + "\'")
                print("Exiting..")
                return
    
    cordoncount = len(dynsp_cordons)
    for i in range(cordoncount):
        cordonstrings.append("local e = null \n\n")    #initialize string list

    print("Analyzing entities within areas..")

    #get entities 
    for entry in results:
        cordonid = test_entity(entry[1])    #test if valid entity to dynamically spawn, and within a cordon
        if entry[0] == 'entity' and cordonid >= 0:  
            count+=1
            cordon_entindex = dynsp_cordons[cordonid][3]
            dynsp_cordons[cordonid][3] += 1
            #adding function wrap around each entity, so they can be spawned in iteratively, with delay
            cordonstrings[cordonid] += f'function SpawnEntity{cordon_entindex}(){{'
            cordonstrings[cordonid] += stringify_entity(entry[1])
            cordonstrings[cordonid] += "}\n\n"
            
            #infodecal entities must precache their assets before creation
            #only infodecals use the "texture" keyvalue, so we can directly search for this
            for kv in entry[1]:
                if kv[0] == 'texture':
                    if kv[1] in must_precache_mat:
                        continue
                    else:
                        must_precache_mat.append(kv[1])
            
            #find id
            id=getid(entry[1])
            #remove the entity from the input vmf
            vmfstr = remove_entity_file(id, vmfstr)
              
    
    out = open(vmf_out, 'w')
    out.write(vmfstr)
    
    #Generate area entity creation function.
    for cordonid in range(cordoncount):
       
        logicscriptname = "DynEnter" + dynsp_cordons[cordonid][0]
       #create logic script initialization
        cordonstrings[cordonid] += f'\
\n\
\nfunction StartAreaSpawn_{dynsp_cordons[cordonid][0]}()\
\n{{\
\n\tprintcl(100,100,200, "Initializing area {dynsp_cordons[cordonid][0]} entity spawn..")\n'
        
        ls_str = ""
        #the bulk of function calls    
        for i in range(dynsp_cordons[cordonid][3]):
            delay = round(i/10.0, 2)
            ls_str += f'\tEntFireByHandle(self, "RunScriptCode", "SpawnEntity{i}()", {delay}, self, self)\n'
        #close brackets
        cordonstrings[cordonid] += ls_str + '}'


        #parse classname types
        classnamescount = len(classnames)
        cordonstrings[cordonid] += '\n\nlocal classnames = [ '
        for index, classname in enumerate(classnames):
            if index != classnamescount-1:
                cordonstrings[cordonid] += f'"{classname}",\n'
            else:
                cordonstrings[cordonid] += f'"{classname}"]\n\n'
            #cordonstrings[cordonid] += cnamesstr


        #Generate area entity destruction function. Premake destruction functions for each cordoned area
        cordonstrings[cordonid] += f'\
\nfunction DestroyEnts_{dynsp_cordons[cordonid][0]}(hDynEnterManager){{     //remove cordoned entities\
\n\tforeach (classname in classnames){{\
\n\t\tlocal ent = null \
\n\t\twhile ( ( ent = Entities.FindByClassnameWithinBox(ent, classname, {dynsp_cordons[cordonid][1]}, {dynsp_cordons[cordonid][2]} ) ) != null ){{\
\n\t\t\tent.AcceptInput("Kill", "", self, self)\
\n\t\t\t}}\
\n\t\t}}\
\n\thDynEnterManager.AcceptInput("Kill", "", null, null) //clean up the script entity as well\
\n}}'
        
    
    #make combined script, to be used on a logic script acting as an area manager
    overlord_scriptstr =  ""
    for cordon_info in dynsp_cordons:
        overlord_scriptstr += f'DoIncludeScript("{vscriptout_relativep}/{cordon_info[0]}.nut", null)\n'
    overlord_scriptstr += "/*\tincludes these functions from includescripts:"
    for cordon_info in dynsp_cordons:   
        overlord_scriptstr += f'\tStartAreaSpawn_{dynsp_cordons[cordonid][0]}()\n'
    for index, cordon_info in enumerate(dynsp_cordons):   
        overlord_scriptstr += f'\tDestroyEnts_{dynsp_cordons[cordonid][0]}(hDynEnterManager)\n'
        if (index == len(dynsp_cordons)-1):
            overlord_scriptstr += "*/"
        
    
    #write compiled vscript functions to files.
    #TODO cap cordons as this has infinite filewrite possibility
    
    #file combining all compiled vscript functions into one place
    out_ol = open(f'{vscriptout_p}/DynEnter_overlord.nut', 'w')
    out_ol.write(overlord_scriptstr)
    #individual area scriptfiles:
    for index, cordon_info in enumerate(dynsp_cordons):
        out = open(f'{vscriptout_p}/{cordon_info[0]}.nut', 'w')
        out.write(cordonstrings[index])
    
    #write precache things to precache file (wip)
    precacheout = open(f'{vscriptout_p}/precache.nut', 'w')
    for texture in must_precache_mat:
        precacheout.write( f'PrecacheMaterial("{texture}")\n' )

    
    #time to show results
    print(f'Found {count} entities in {cordoncount} cordons:')
    for i in range(cordoncount):
        print( dynsp_cordons[i][0] + ": " + str(dynsp_cordons[i][3]))
    for index, count in enumerate(entfound_count):
        print(f'{classnames[index]}: {count}')
    
    print(f'COMPILE_PAL_SET file "{vmf_out}"')




















def remove_entity_file(id, vmfstr):
    r = re.compile('entity\n{\n\t"id" "'+ str(id) +'".*?}\n}', re.DOTALL)
    #obj = r.search(vmfstr)
    return r.sub('', vmfstr)

#return entity id
def getid(entity_data):
    for kv in entity_data:
        if isinstance(kv[1], str):
            if kv[0] == 'id':
                return kv[1]


def get_script_path():
    return os.path.dirname(os.path.realpath(sys.argv[0]))

def is_inside_cordon(point, boxMins, boxMax):
    
    #evaluate if point lies within x y or z min/max
    if boxMins[0] >= point[0] or point[0] >= boxMax[0] or        boxMins[1] >= point[1] or point[1] >= boxMax[1] or        boxMins[2] >= point[2] or point[2] >= boxMax[2]:
        return False
    else:    
        return True
    
    
#return cordon id in cordon_info list if entity in cordon, -1 if not found
def is_inside_cordons(point):

    for index, cordon_info in enumerate(dynsp_cordons):
        if is_inside_cordon(point, cordon_info[1], cordon_info[2]):
            return index
    return -1



#   return true if valid entity, and is within a cordon
def test_entity(entity_data):
    
    for kv in entity_data:
        if kv[0] == 'classname':
            if kv[1] == '' or not kv[1] in classnames:
                return -1

        if isinstance(kv[1], str):
            if kv[0] == 'origin':
                return is_inside_cordons(list(map(float, kv[1].split())))
            
        if cfg_skip_named_ents == True and kv[0] == 'targetname':
            if kv[1] != '':
                return -1
            
        if not isinstance(kv[1], str) and kv[0] == 'solid':    # no solids
            return -1


def stringify_entity(entity_data):
    tierkv = ''
    tierconn = ''
    classname = ''
    bInfoDecal = False
    for kv in entity_data:
        if kv[0] == 'classname':
            classname = kv[1]
            entfound_count[classnames.index(classname)] += 1    #count classname occurances cause stats are great
            
        # if kv[0] == 'texture':  #mark as infodecal
        #     bInfoDecal = True
            
    entsp_info = []
    for kv in entity_data:
        
        if isinstance(kv[1], str):
            if kv[0] != 'id' and kv[0] != 'classname':
                entsp_info.append(f'\t{kv[0]} = "{kv[1]}"')
        elif kv[0] == 'connections':
            for conn in kv[1]:
                params = conn[1].split(',')
                tierconn += f'e.AddOutput("{conn[0]}", "{params[0]}", "{params[1]}", "{params[2]}", {params[3]}, {params[4]})\n'


    outstr = f'\ne = SpawnEntityFromTable("{classname}",\n{{\n'
    item_len = len(entsp_info)-1
    for index, item in enumerate(entsp_info):
        outstr += item
        if index != item_len:
            outstr += ",\n"
        else :
            outstr += "\n});\n"
    # if bInfoDecal:
    #     outstr      += '\ne.AcceptInput("Activate", "", null, null)\n'
        
    if len(tierconn):
        outstr += tierconn

    return outstr




#   return: true if cordons with correct names found
def index_cordons(cordons_table):
    for cordon in cordons_table:
        if cordon[0] == 'cordon':
                        
            name    = ''
            pointList  = []
            for kv in cordon[1]:
                if kv[0] == 'name' and cordonprefix in kv[1]:
                    name = kv[1].split('_')[1]
                    
            if not name:
                continue
            
            
            
            for kv in cordon[1]:
                if kv[0] == 'box':
                    char_to_replace = {'(' : '', ')' : '' }
                    
                    pointMin = kv[1][0][1]
                    pointMax = kv[1][1][1]
                    
                    for key, value in char_to_replace.items():
                        pointMin = pointMin.replace(key, value)
                        pointMax = pointMax.replace(key, value)
                        
                    pointList.append(pointMin.split())
                    pointList.append(pointMax.split())
            

            dynsp_cordons.append( [name, [float(pointList[0][0]), float(pointList[0][1]), float(pointList[0][2])], [float(pointList[1][0]), float(pointList[1][1]), float(pointList[1][2])], 0 ] )
            
    if len(dynsp_cordons):
        return True
    else:
        return False
            
    # for cordon in dynsp_cordons:
    #     print(cordon)
            






if __name__ == '__main__':
    main(sys.argv[1])

        
    
    


