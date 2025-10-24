import System
import clr
clr.AddReference("RevitNodes")
clr.AddReference('RevitAPI')
from Autodesk.Revit.DB import *
from Autodesk.Revit.DB import FilteredElementCollector, CurveLoop
from Autodesk.Revit.DB.Architecture import *
clr.AddReference('RevitServices')
import RevitServices
from RevitServices.Persistence import DocumentManager
from RevitServices.Transactions import TransactionManager
from Revit.Elements import *
from Autodesk.Revit.DB import FamilyInstance, Family
clr.ImportExtensions(RevitServices.Elements)

import math

 
doc = DocumentManager.Instance.CurrentDBDocument
view = doc.ActiveView
sketch_plane = view.SketchPlane

rooms = FilteredElementCollector(doc, doc.ActiveView.Id).OfCategory(BuiltInCategory.OST_Rooms).WhereElementIsNotElementType().ToElements()

all_doors = FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Doors).WhereElementIsNotElementType().ToElements()
# Get all windows in the document
all_windows = FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Windows).WhereElementIsNotElementType().ToElements()
all_ceiling = FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Ceilings).WhereElementIsNotElementType().ToElements()



#get all family needed to be add from dynamo
family_vent_mamad = IN[0] if str(IN[0]) != None else None
family_elevation_triangle = IN[1] if str(IN[1]) != None else None
family_entrance_triangle = IN[2] if str(IN[2]) != None else None
family_balcony_triangle = IN[3] if str(IN[3]) != None else None
family_vent_close = IN[4] if str(IN[4]) != None else None
family_room_tag = IN[5] if str(IN[5]) != None else None
filter_vent_close = IN[6] #boolean

family_asterist_1 = IN[7] if str(IN[7]) != None else None
family_asterist_2 = IN[8] if str(IN[8]) != None else None
family_asterist_3 = IN[9] if str(IN[9]) != None else None

LOWER_CEILING_DIFF = 10 #cm IN[7] maybe
SQR_OF_3 = 1.732
FEET_TO_CM = 30.48
family_sum_created = [0]*5
errors = []
output = []
view__cropped_shape = []
rooms_n_bbs = []

def get_linked_elements():
    # Collect all RevitLinkInstances in the document
    link_instances_collector = FilteredElementCollector(doc).OfClass(RevitLinkInstance).ToElements()

    for link_instance in link_instances_collector:
        # Get the linked document
        linked_doc = link_instance.GetLinkDocument()

        if linked_doc:
            # Apply a bounding box filter for elements visible in the active view
            # view_bounding_box = view.CropBox
            # offset =15
            # outline = Outline((view_bounding_box.Min - XYZ(offset, offset, offset)), (view_bounding_box.Max + XYZ(offset, offset, offset)))
            # bounding_box_filter = BoundingBoxIntersectsFilter(outline)

            # Collect elements from the linked document that are within the bounding box
            global rooms
            global all_doors
            global all_windows
            global all_ceiling
            
            #.WherePasses(bounding_box_filter)
            all_rooms = list(rooms)
            all_rooms.extend(FilteredElementCollector(linked_doc).\
            OfCategory(BuiltInCategory.OST_Rooms)\
            .WhereElementIsNotElementType().ToElements()) 
          
            rooms = list(all_rooms)
            
            doors = list(all_doors)
            doors.extend(FilteredElementCollector(linked_doc).\
            OfCategory(BuiltInCategory.OST_Doors)\
            .WhereElementIsNotElementType().ToElements())
            
            all_doors = list(doors)


            windows = list(all_windows)
            windows.extend(FilteredElementCollector(linked_doc).\
            OfCategory(BuiltInCategory.OST_Windows)\
            .WhereElementIsNotElementType().ToElements())
            
            all_windows = list(windows)

            ceiling = list(all_ceiling)
            ceiling.extend(FilteredElementCollector(linked_doc).\
            OfCategory(BuiltInCategory.OST_Ceilings)\
            .WhereElementIsNotElementType().ToElements())
            all_ceiling = list(ceiling)

def update_crop_shape():
     # Check if the view has a non-rectangular crop
    if not view.CropBoxActive or view.CropBoxVisible:
        errors.append("No crop view found")
    
    # Get the crop shape
    crop_manager = view.GetCropRegionShapeManager()
    crop_shape = crop_manager.GetCropShape()
    
    if crop_shape is None or len(crop_shape) == 0:
        errors.append("No crop view found")
    
    # The crop shape is a list of curves
    global view__cropped_shape 
    view__cropped_shape.extend(crop_shape)


def update_sum_created(family_item):
    if family_item == family_vent_mamad:
        family_sum_created[0] += 1
    elif family_item == family_elevation_triangle:
        family_sum_created[1] += 1
    elif family_item == family_entrance_triangle:
        family_sum_created[2] += 1
    elif family_item == family_balcony_triangle:
        family_sum_created[3] += 1
    elif family_item == family_vent_close:
        family_sum_created[4] += 1

def mamad_vetilation_is_needed(room_name):
    if family_vent_mamad is not None:
        if "ממד" in room_name:
            return True       
    return False

def closed_room_vetilation_is_needed(room):
    room_name = room_to_name(room)
    if family_vent_close is not None:
        if "רחצה" in room_name or "שירותים" in room_name or "מטבח" in room_name:
            if not window_in_room(room) or not filter_vent_close:
                return True
    return False

           

def is_room_elevation_needed(room_names): 
    if family_elevation_triangle is None:
        return False
    for i, room_name in enumerate(room_names):
        #if the door connects one of the following rooms
        if "מבואה קומתית" in room_names or "לובי" in room_names and len(room_names) == 2: #if it is entrance
            return True
        if ("מטבח" in room_name or "ח. דיור" in room_name or "ח. מגורים" in room_names or "סלון" in room_names) and len(room_names) == 1: #if it is entrance
            return True
        if "ממד" in room_name: 
            return True
        if "מרפסת" in room_name:
            return True
        if "רחצה" in room_name:
            return True
        if "שירותים" in room_name:
            return True
    return False

def GetRoomAtPoint(p1):
    for room_n_bb in rooms_n_bbs:
        min_point = room_n_bb[1][1]
        max_point = room_n_bb[1][0]
        in_x = p1.X >= min_point.X and p1.X <= max_point.X
        in_y = p1.Y >= min_point.Y and p1.Y <= max_point.Y
        in_z = p1.Z >= min_point.Z and p1.Z <= max_point.Z

        if in_x and in_y and in_z:
            return room_n_bb[0]
    return

def which_wall_element_on(element, room): #left\right\up\down
    is_horizontal = (round(element.Location.Rotation*(180/math.pi)))%180 == 0 
    #what dimension of the door element is bigger, if its x_diif so it is_horizontal
    if is_horizontal == None:
        p_max = element.get_BoundingBox(None).Max
        p_min = element.get_BoundingBox(None).Min
        x_diff = p_max.X - p_min.X
        y_diff = p_max.Y - p_min.Y
        is_horizontal =  x_diff > y_diff

    z_floor = view.GenLevel.Elevation
    offset = XYZ(2,2,0)
    if is_horizontal:
        offset = XYZ(2,2,0)

    point1 = get_center_bbox(element) + offset
    point2 = get_center_bbox(element) - offset
    # Find rooms at these points

    room1 = GetRoomAtPoint(point1) #right/up
    room2 = GetRoomAtPoint(point2) #left/down

    # if room.Id == ElementId(6074107):
    #     output.append([ room_to_name(room1), room_to_name(room2)])

      

    # output.append(["a", point1, room_to_name(room1),point2,  room_to_name(room2)]) 
    # output.append([is_rotation_horizontal, room_to_name(room1), room_to_name(room2)])
    if room1 is None and room2 is None:
        return
    if room1 is None:
        if room2.Id == room.Id:
            if is_horizontal:
                return "up"
            else:
                return "right"
    if room2 is None:
        if room1.Id == room.Id:
            if is_horizontal:
                return "down"
            else:
                return "left"
    
    if room1 is not None and room1.Id == room.Id:
            if is_horizontal:
                return "down"
            else:
                return "left"        
    if room2 is not None and room2.Id == room.Id:
            if is_horizontal:
                return "up"
            else:
                return "right"
    #didn't worked so put it visible with a guess
    if is_horizontal:
        return "down"
    else:
        return "left"


def set_room_tag(room):
    z_floor = view.GenLevel.Elevation
    # Get the location point of the room
    point = room.Location.Point
    
    # Create a UV object from the XY values of the point
    uv = UV(point.X, point.Y)
    
    # Create the room tag
    TransactionManager.Instance.EnsureInTransaction(doc)
    room_tag = doc.Create.NewRoomTag(LinkElementId(room.Id), uv, doc.ActiveView.Id)
    
    new_location = XYZ(room_tag.Location.Point.X, room_tag.Location.Point.Y, z_floor)
    room_tag.Location.Move(new_location.Subtract(room_tag.Location.Point))  

    room_name = room.get_Parameter(BuiltInParameter.ROOM_NAME).AsString()

    # output.append([room_tag.Id, room_name, room_tag.Location.Point])
    if family_room_tag is not None:
        element_id = ElementId(family_room_tag.Id) # Convert the ID to ElementId
        # Get the element
        family_elemenet = doc.GetElement(element_id)
        if family_elemenet:
            family_symbols = family_elemenet.GetFamilySymbolIds()  # Get a set of ElementIds
            if family_symbols:
                # Iterate through the family symbols (ElementIds)
                for symbol_id in family_symbols:
                    family_symbol = doc.GetElement(symbol_id)  # Get the FamilySymbol object
                    if family_symbol is not None:
                        # Ensure the symbol is active
                        if not family_symbol.IsActive:
                            family_symbol.Activate()
                        # Set the tag type
                        room_tag.ChangeTypeId(family_symbol.Id)
    TransactionManager.Instance.TransactionTaskDone()
    

def rotate_the_element (new_instance, location_point, degrees):
    # Create a rotation axis (vertical vector)
    axis_vector = XYZ.BasisZ
    
    # Convert degrees to radians
    angle_radians = degrees * (math.pi / 180)
    
    # Rotate the instance
    ElementTransformUtils.RotateElement(doc, new_instance.Id,\
    Line.CreateBound(location_point, location_point.Add(axis_vector)), angle_radians) 

#add mark instance from family 
def create_instance_from_family(location_point, family_item, rotation_degrees):
    #family_box = clr.StrongBox[Family]()
    
    element_id = ElementId(family_item.Id) # Convert the ID to ElementId
    # Get the element
    family_elemenet = doc.GetElement(element_id)
    if family_elemenet:
        family_symbols = family_elemenet.GetFamilySymbolIds()  # Get a set of ElementIds
        if family_symbols:
            # Iterate through the family symbols (ElementIds)
            for symbol_id in family_symbols:
                family_symbol = doc.GetElement(symbol_id)  # Get the FamilySymbol object
                if family_symbol is not None:
                    # Ensure the symbol is active
                    if not family_symbol.IsActive:
                        family_symbol.Activate()
                    move_coor = XYZ(0, 0, 0)
                    if family_item == family_entrance_triangle:
                        move_coor =XYZ(0,-1,0)
                    elif family_item == family_asterist_1 or family_item == family_asterist_2 or family_item == family_asterist_3:
                        move_coor =XYZ(0, 0.8, 0)
                    # Create a new instance in room location
                    # if family_item == family_elevation_triangle:
                    TransactionManager.Instance.EnsureInTransaction(doc)
                    new_instance = doc.Create.NewFamilyInstance((location_point+move_coor), family_symbol, doc.ActiveView)
                    update_sum_created(family_item)
                    if rotation_degrees != 0:
                        rotate_the_element(new_instance, location_point, rotation_degrees)
                    TransactionManager.Instance.TransactionTaskDone()

  
                    

def side_to_rotate(side_of_door):
    if side_of_door == "up":
        return 180
    elif side_of_door == "down":
        return 0
    elif side_of_door == "right":
        return 90
    elif side_of_door == "left":
        return 270
    else:
        return 0

def is_entrance_door(room_names):
    if family_entrance_triangle is None:
        return False
    for room_name in room_names:
        if "מעליות" in room_name or "חדר מדרגות" in room_name:
            return False
        if "מבואה קומתית" in room_name and len(room_names) == 2:
            return True
        if "לובי" in room_name and len(room_names) == 2:
            return True
        if ("ח. דיור" in room_name or "ח. מגורים" in room_name or "סלון" in room_name) and len(room_names) == 1:
            return True
        if "מטבח" in room_name and len(room_names) == 1:
            return True
    return False

def room_to_name(room):
    if room and room.get_Parameter(BuiltInParameter.ROOM_NAME):
        room_name = room.get_Parameter(BuiltInParameter.ROOM_NAME).AsString().strip()
        room_name = room_name.replace('"',"")
        return room_name
    return ""


def empty_room(room):
    if not room:
        return True
    elif room.get_BoundingBox(doc.ActiveView) == None:
        return True
    elif room.Location == None or room.Location.Point == None:
        return True
    elif room.get_Parameter(BuiltInParameter.ROOM_NAME) == None or room.get_Parameter(BuiltInParameter.ROOM_NAME).AsString() == "":
        return True
    else:
        return False

def room_not_in_appartment(room):
    z_floor = view.GenLevel.Elevation
    if room.Location.Point.Z != z_floor:
        return True
    
    room_name = room_to_name(room)
    rooms_outside = ["מבואה", "לובי", "חדר מדרגות", "מעליות"]
    for room_outside in rooms_outside:
        if room_outside in room_name:
            return True
    return False

def is_mamad_door(room_names):
    if family_asterist_3 != None:
        for room_name in room_names:
            if "ממד" in room_name:
                return True
    return False 

def is_1_asterisk_door(room_names):
    if family_asterist_1 != None:
        if is_entrance_door(room_names):
            return True
        for room_name in room_names:
            if "מחסן" in room_name or "רחצה" in room_name or "שירותים" in room_name:
                return True
    return False

def is_2_asterisk_door(room_names):
    if family_asterist_2 != None:
        for room_name in room_names:
            if "מרפסת" in room_name:
                return True
    return False

def filter_relevant_rooms(rooms): #delete empty & duplicate
   rooms_not_empty = [room for room in rooms if not empty_room(room)] #delete empty
    
   #remove rooms that are not in the appartment
   rooms_in_view = [room for room in rooms_not_empty if is_in_cropped_view(room.Location.Point)]

   rooms_in_appartment = [room for room in rooms_in_view if not room_not_in_appartment(room)]

   rooms_locations = [room.Location.Point for room in rooms_in_appartment]
    #delete duplicate rooms with same locations
   rooms_not_duplicate = [room for index, room in enumerate(rooms_in_appartment) if room.Location.Point not in rooms_locations[:index]]

   rooms_bbs = [[room.get_BoundingBox(None).Max, room.get_BoundingBox(None).Min] for room in rooms_not_duplicate]
   global rooms_n_bbs
   rooms_n_bbs = list(zip(rooms_not_duplicate, rooms_bbs))

   return rooms_not_duplicate

    
def doors_to_print(doors):
    room_names = []
    for door in doors:
        phase = doc.GetElement(door.CreatedPhaseId)
        rooms_of_door = [door.FromRoom[phase], door.ToRoom[phase]]
        room_names.append([room_to_name(room) for room in rooms_of_door\
                           if room and room.Location and room.Location.Point] )
    return room_names

def is_in_cropped_view(point):
    global view__cropped_shape

    # Ray casting algorithm
    count = 0
    for curve in view__cropped_shape[0]:
        p1 = curve.GetEndPoint(0)
        p2 = curve.GetEndPoint(1)
        if ((p1.Y > point.Y) != (p2.Y > point.Y)) and \
           (point.X < (p2.X - p1.X) * (point.Y - p1.Y) / (p2.Y - p1.Y) + p1.X):
            count += 1
    return count % 2 == 1


def get_center_bbox(item):
    return (item.get_BoundingBox(None).Min + item.get_BoundingBox(None).Max) / 2

def get_location_point(item):
     if item.Category.Name.strip() == "Ceilings":
         return get_center_bbox(item)
     else:
         return item.Location.Point

def filter_all_elements(all_elements): #door/windows delete empty & duplicate, and only with same level
   #delete elements that are not in the same level
   elements_same_level = [element for element in all_elements if element.LevelId == view.GenLevel.Id and element.Location]
   elements_in_view = [e for e in elements_same_level if is_in_cropped_view(get_location_point(e))]
   
   if len(elements_in_view) == 0:
        return []
   
   if elements_in_view[0].Category.Name.strip() == "Windows" or elements_in_view[0].Category.Name.strip() == "Ceilings": #return if element is windows
        return elements_in_view
   
   if elements_in_view[0].Category.Name.strip() == "Doors":
        doors_to_delete = []
        for door in elements_in_view:
            phase = doc.GetElement(door.CreatedPhaseId)
            rooms_of_door = [door.FromRoom[phase], door.ToRoom[phase]]
            rooms_of_door_not_empty = [room for room in rooms_of_door if not empty_room(room)]
            room_names = rooms_to_names(rooms_of_door_not_empty)
            
            if "מעליות" in room_names or "חדר מדרגות" in room_names:
                    doors_to_delete.append(door)
        
        for door_to_delete in doors_to_delete:
            if door_to_delete in elements_in_view:
                elements_in_view.remove(door_to_delete)
   
   return elements_in_view

def is_a_balcony_entrance(room_names):
    if family_balcony_triangle is None:
        return False
    if len(room_names) == 2:
        for room_name in room_names:
            if "מרפסת" in room_name:
                return True
    return False

def rooms_to_names(rooms):
    return [room_to_name(room) for room in rooms if not empty_room(room)]

def window_in_room(room):
    # Get the bounding box of the room
    room_bb = room.get_BoundingBox(None)
    # Check each window
    for window in windows:
        # Get the center point of the window
        window_loc = window.Location.Point
        xy_offset = 1
        z_offset = 0.1
        # Check if the window's center point is within the room's bounding box
        if (room_bb.Min.X - xy_offset <= window_loc.X <= room_bb.Max.X + xy_offset and
              room_bb.Min.Y - xy_offset <= window_loc.Y <= room_bb.Max.Y + xy_offset and
            room_bb.Min.Z + z_offset <= window_loc.Z <= room_bb.Max.Z - z_offset):
            return True
    
    return False

def windows_vitrines_to_rooms(windows):
    rooms_of_window = []
    
    for window in windows:

        window_family_name = window.Symbol.Family.Name.lower()
        if "vitrina" in window_family_name: #if it is a vitrine
           
            # Find the center point of the window
            center_of_wall = window.Location.Point

            if center_of_wall is not None: 
                # Create offset points on both sides of the window
                direction = window.FacingOrientation
                # Small offset to ensure we're inside the rooms
                point1 = center_of_wall + direction + XYZ(0,0,1)
                point2 = center_of_wall - direction + XYZ(0,0,1)
                # Find rooms at these points
                room1 = doc.GetRoomAtPoint(point1)
                room2 = doc.GetRoomAtPoint(point2)
               
                if room1 is not None or room2 is not None:
                    rooms_of_window.append([window, room1, room2])
    
    return rooms_of_window

def delete_old_symbols_tags():
    room_tags = FilteredElementCollector(doc, doc.ActiveView.Id).OfCategory(BuiltInCategory.OST_RoomTags).WhereElementIsNotElementType().ToElements()
    for room_tag in room_tags:
        TransactionManager.Instance.EnsureInTransaction(doc)
        doc.Delete(room_tag.Id)
        TransactionManager.Instance.TransactionTaskDone()

    families = [family_vent_mamad, family_balcony_triangle, family_elevation_triangle,\
                   family_entrance_triangle, family_vent_close, family_asterist_1,\
                      family_asterist_2, family_asterist_3]
    family_names = [family.Name for family in families if family is not None]

    #Create a filter for the specific family name
    for family_name in family_names:
        # Create a filtered element collector
        collector_family_instances = FilteredElementCollector(doc, doc.ActiveView.Id).OfClass(FamilyInstance)
        # Create a filter for the specific family name
        family_param_id = ElementId(BuiltInParameter.ELEM_FAMILY_PARAM)
        family_name_rule = ParameterFilterRuleFactory.CreateEqualsRule(family_param_id, family_name, False)
        family_name_filter = ElementParameterFilter(family_name_rule)
    
        # Apply the filter to the collector
        elements = collector_family_instances.WherePasses(family_name_filter).WhereElementIsNotElementType().ToElements()
        # Create a list to store element ids
        element_ids = [element.Id for element in elements]

        TransactionManager.Instance.EnsureInTransaction(doc)
        for element_id in element_ids:
            doc.Delete(element_id)
        TransactionManager.Instance.TransactionTaskDone()

      
#includes entrance_door\elevation change symbol\balcony exit
def add_all_doors_symbols(doors):
    for door in doors:
        location = door.Location
        if isinstance(location, LocationPoint): #if door is a real object
            door_location = location.Point
            phase = doc.GetElement(door.CreatedPhaseId)
        
            # Get the rooms name on both sides of the door
            rooms_of_door = [door.FromRoom[phase], door.ToRoom[phase]]
            room_names = rooms_to_names(rooms_of_door)
            
            if is_entrance_door(room_names): #entrance door
                room_to_check = rooms_of_door[0] #the enrance room ח.מגורים
               
                if  empty_room(room_to_check) or "מבואה קומתית" in room_to_name(room_to_check) or "לובי" in room_to_name(room_to_check):
                    room_to_check = rooms_of_door[1]
               
                #determine where is the door up/down/left/right wall
                side_of_door = which_wall_element_on(door, room_to_check)
                rotate_degrees = side_to_rotate(side_of_door)
            
                #create an instance of family_entrance_triangle symbol
                create_instance_from_family(door_location, family_entrance_triangle, rotate_degrees)
              


            if is_room_elevation_needed(room_names): #if door is between several rooms or entrance door
                is_rotation_horizontal =  (round(math.degrees(location.Rotation)) % 180 == 0)
                rotate_degrees = 0 if is_rotation_horizontal else 90
                
                #create an instance of family_elevation_triangle symbol
                create_instance_from_family(door_location, family_elevation_triangle, rotate_degrees)
            
            if is_a_balcony_entrance(room_names):
                room_to_check = rooms_of_door[0] if rooms_of_door[0] != None else rooms_of_door[1]
                if rooms_of_door[0] != None and rooms_of_door[1] != None:
                    #the room that is not the balcony
                    room_to_check = rooms_of_door[1] if "מרפסת" in room_to_name(rooms_of_door[0]) else rooms_of_door[0] 

                #determine where is the door up/down/left/right wall
                side_of_door = which_wall_element_on(door, room_to_check)
                rotate_degrees = side_to_rotate(side_of_door)

                rotate_degrees = (rotate_degrees+ 180) % 360

                #create an instance of family_balcony_triangle symbol
                create_instance_from_family(door_location, family_balcony_triangle, rotate_degrees) 
                family_sum_created[2] -= 1
                family_sum_created[3] += 1
                 

            if is_1_asterisk_door(room_names): #מרפסת/רחצה/שירותים/מחסן או כניסה
                room_to_check = rooms_of_door[0] #the enrance room ח.מגורים
                if "רחצה" in room_to_name(rooms_of_door[1]) or "שירותים" in room_to_name(rooms_of_door[1]) or "מחסן" in room_to_name(rooms_of_door[1]):
                     room_to_check = rooms_of_door[1]
                elif empty_room(room_to_check) or "מבואה קומתית" in room_to_name(room_to_check) or "לובי" in room_to_name(room_to_check):
                    room_to_check = rooms_of_door[1]

                #determine where is the door up/down/left/right wall
                side_of_door = which_wall_element_on(door, room_to_check)
                # output.append([room_to_check.Id, side_of_door])
                rotate_degrees = side_to_rotate(side_of_door)

                #1 asterisk symbol for entrance
                create_instance_from_family(door_location, family_asterist_1, rotate_degrees)

            if is_2_asterisk_door(room_names):  
                room_to_check = rooms_of_door[0] if rooms_of_door[0] != None else rooms_of_door[1]
                if rooms_of_door[0] != None and rooms_of_door[1] != None:
                    #the room that is not the balcony
                    room_to_check = rooms_of_door[1] if "מרפסת" in room_to_name(rooms_of_door[0]) else rooms_of_door[0] 

                #determine where is the door up/down/left/right wall
                side_of_door = which_wall_element_on(door, room_to_check)
                rotate_degrees = side_to_rotate(side_of_door)
                rotate_degrees = rotate_degrees

                 #2 asterisk symbol for entrance
                create_instance_from_family(door_location, family_asterist_2, rotate_degrees)

            if is_mamad_door(room_names):   
                room_to_check = rooms_of_door[0] 
                if "ממד" in room_to_name(rooms_of_door[1]):
                    room_to_check = rooms_of_door[1]

                side_of_door = which_wall_element_on(door, room_to_check)
                rotate_degrees = side_to_rotate(side_of_door)
                #3 asterisk symbol for entrance
                create_instance_from_family(door_location, family_asterist_3, rotate_degrees)
 
           
def add_vitrine_symbols(vitrine_windows):
    for window, room1, room2 in vitrine_windows:
        room_names = rooms_to_names([room1, room2])
        # z_floor = round(view.GenLevel.Elevation, 2)

        if is_a_balcony_entrance(room_names) or ((room1 is None or room2 is None)): #if there is one room near vitrina is empty it is exit to balcony or garden 
            room_to_check = room1 if room1 != None else room2
            if room1 != None and room2 != None:
                room_to_check = room2 if "מרפסת" in room_to_name(room1) else room1 #the room that is not the balcony

            #determine where is the window up/down/left/right wall
            side_of_window = which_wall_element_on(window, room_to_check)

            rotate_degrees = side_to_rotate(side_of_window)
            asteriskt_rotate_degrees = rotate_degrees
            rotate_degrees = (rotate_degrees+ 180) % 360

            #create an instance of family_balcony_triangle
            create_instance_from_family(window.Location.Point, family_balcony_triangle, rotate_degrees)
            family_sum_created[2] -= 1
            family_sum_created[3] += 1

            if family_asterist_2 is not None:
                #2 asterisk symbol for entrance
                create_instance_from_family(window.Location.Point, family_asterist_2, asteriskt_rotate_degrees)

        if is_room_elevation_needed(room_names):
            #create an instance of family_elevation_triangle
            create_instance_from_family(window.Location.Point, family_elevation_triangle, rotate_degrees)

def add_all_rooms_symbols(rooms):
    for room in rooms:
        if room is not None and room.Location is not None: #not empty
            room_name = room_to_name(room)
            set_room_tag(room)
            below_room_tag = room.Location.Point - XYZ(0,1,0)

            if mamad_vetilation_is_needed(room_name): #add to MAMAD room an air ventilation symbol
                #create an instance of circle air ventilation symbol      
                create_instance_from_family(below_room_tag, family_vent_mamad, 0)
            

            if closed_room_vetilation_is_needed(room): #Venta ventelation     
                #create an instance of venta double circle symbol
                create_instance_from_family(below_room_tag, family_vent_close, 0)

def create_ceiling_lines(curve_edges):
    z_floor = view.GenLevel.Elevation
    lines = []
    points = []
    if len(curve_edges) == 12: #rectangle box
        for curve in curve_edges[:4]:
            points.append(XYZ(curve.GetEndPoint(0).X, curve.GetEndPoint(0).Y, z_floor)) #take only the bottom face of rectangle
        
        lines.append(Line.CreateBound(points[0], points[2]))
        lines.append(Line.CreateBound(points[1], points[3]))
    else: 
        base_of_ceiling_z = curve_edges[0].GetEndPoint(0).Z
        #take only the bottom face of the shape
        curves_edges_level = [curve for curve in curve_edges if curve.GetEndPoint(0).Z == base_of_ceiling_z and curve.GetEndPoint(1).Z == base_of_ceiling_z]

        # output.append(len(curves_edges_level))
        # for curve in curves_edges_level:
        #     output.append(["here:", curve.GetEndPoint(0), curve.GetEndPoint(1)])
        for curve in curves_edges_level:
            start_point = XYZ(curve.GetEndPoint(0).X, curve.GetEndPoint(0).Y, z_floor)
            end_point = XYZ(curve.GetEndPoint(1).X, curve.GetEndPoint(1).Y, z_floor)
            try: #create all lines the surronding the lower ceiling
                line = Line.CreateBound(start_point, end_point)
            except:
                continue
            lines.append(line)


    # Get the "Overhead Small" line style
    line_styles = FilteredElementCollector(doc).OfClass(GraphicsStyle).ToElements()
    overhead_small_style = next((ls for ls in line_styles if ls.Name == "Overhead Small"), None)

    if overhead_small_style is None:
        print("Overhead Small line style not found.")
    else:
        # Create the detail line
        for line in lines:
            TransactionManager.Instance.EnsureInTransaction(doc)
            detail_line = doc.Create.NewDetailCurve(doc.ActiveView, line)
            
            # Set the line style
            detail_line.LineStyle = overhead_small_style
            TransactionManager.Instance.TransactionTaskDone()


def ceiling_get_height(ceiling):
    level_height = view.GenLevel.Elevation
    ceiling_z = ceiling.get_BoundingBox(None).Min.Z
    return round((ceiling_z - level_height) * FEET_TO_CM)


def filter_only_lower_ceiling(ceilings):
    if len(ceilings) == 0:
        return
    ceilings_z_cm = [ceiling_get_height(ceiling) for ceiling in ceilings]
    max_ceiling_height = max(ceilings_z_cm)
    ceilings_no_max = [c for c in ceilings if ceiling_get_height(c) <= (max_ceiling_height - LOWER_CEILING_DIFF)] #10cm

    return ceilings_no_max


def mark_lower_ceiling(ceilings):
    ceilings_no_max = filter_only_lower_ceiling(ceilings)
  
    if ceilings_no_max != None:
        for ceiling in ceilings_no_max:
            geo_element = ceiling.get_Geometry(Options())
            boundary_curves = []
        
            # Iterate through the geometry objects
            for geo_obj in geo_element:
                if isinstance(geo_obj, Solid):
                    # Get the edges of the solid
                    edges = geo_obj.Edges
                    for edge in edges:
                        # Add the curve of each edge to the boundary curves list
                        boundary_curves.append(edge.AsCurve())
                
            
            create_ceiling_lines(boundary_curves)
     
def errors_to_user():
    if len(rooms) == 0:
        errors.append("No rooms in view")
    if family_elevation_triangle is None:
        errors.append("no elevation change family was found, check if you wrote it correctly & the family rfa file is loaded to project")
    if family_entrance_triangle is None:
        errors.append("no exit appartment arrow family was found,check if you wrote it correctly & the family rfa file is loaded to project")
    if family_balcony_triangle is None:
        errors.append("no balcony entrance arrow family was found, check if you wrote it correctly & the family rfa file is loaded to project")
    if family_vent_mamad is None:
        errors.append("no mamad vetilation family was found, check if you wrote it correctly & the family rfa file is loaded to project")
    if family_vent_close is None:
        errors.append("no Avrar Meulatz family was found, check if you wrote it correctly & the family rfa file is loaded to project")
    if family_room_tag is None:
        errors.append("no Room Tag family was found, check if you wrote it correctly & the family rfa file is loaded to project")
    if family_asterist_1 is None or family_asterist_2 is None or family_asterist_3 is None:
        errors.append("at least one of asterisk */**/*** family was found, check if you wrote it correctly & the family rfa file is loaded to project")
    output.append(errors)

def output_result():
    result = []
    result.append(str(family_sum_created[0]) + " Mamad ventelation added")
    result.append(str(family_sum_created[1]) + " Elevation arrow added")
    result.append(str(family_sum_created[2]) + " Exit appartment arrown added")
    result.append(str(family_sum_created[3]) + " Balcony entrance arrow added")
    result.append(str(family_sum_created[4]) + " Avrar Meulatz vetilation added")   

    output.append(result)
    

if True: # if __name__ == "__main__":
    # Check if the active view is a floor plan view
    if not isinstance(doc.ActiveView, ViewPlan):
        errors.append("Please run this script in a floor plan view.")
    else:
        update_crop_shape()
        #override old symbols
        delete_old_symbols_tags()

        get_linked_elements()
        windows = filter_all_elements(all_windows)
        rooms = filter_relevant_rooms(rooms)
        
        doors = filter_all_elements(all_doors)
        ceilings = filter_all_elements(all_ceiling)

        add_all_doors_symbols(doors) #includes entrance_door\elevation change symbol\balcony exit

        vitrine_windows = windows_vitrines_to_rooms(windows) #[window, room1, room2]

        add_vitrine_symbols(vitrine_windows) #includes elevation change symbol\balcony exit

        add_all_rooms_symbols(rooms) #includes Mamad ventilation\Venta Ventilation and Room Tag 

        mark_lower_ceiling(ceilings)

        errors_to_user()

        output_result() #counts all intances that were addded


OUT = output
