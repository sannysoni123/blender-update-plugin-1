# Required Blender information.
from bpy.types import Operator
from bpy.props import StringProperty, BoolProperty, EnumProperty
from bpy_extras.io_utils import ExportHelper
from bpy.types import (Panel, Operator, PropertyGroup)
import os
import base64
import requests
import json
import uuid
import bpy
import bpy.utils.previews
from . import addon_updater_ops
# global variable to store icons in
custom_icons = None

## Set custom icons path at blender config directory level
## Comment out following path while run script locally
## Link : https://blender.stackexchange.com/questions/41565/loading-icons-into-custom-addon
icons_dir = os.path.join(os.path.dirname(__file__), "icons")

bl_info = {
    "name": "Swivel Exporter",
    "author": "sannysoni123",
    "version": (1, 0),
    "blender": (2, 80, 0),
    "location": "File > Export > Swivel",
    "description": "Swivel Exporter custom",
    "warning": "",
    "wiki_url": "https://github.com/sannysoni123/blender-update-plugin-1",
    "tracker_url": "https://github.com/sannysoni123/blender-update-plugin-1/issues",
    "category": "Import-Export"
}

def ShowMessageBox(message="", title="Message Box", icon='WARNING'):
    def draw(self, context):
        self.layout.label(text=message)
    bpy.context.window_manager.popup_menu(draw, title=title, icon=icon)


def write_some_data(context, filepath, use_some_setting):
    fileName = os.path.basename(filepath)

    ## Export file in .glb format in local system
    bpy.ops.export_scene.gltf(filepath=filepath, export_format='GLB')
    uuidValue = str(uuid.uuid1())

    ## Fetch s3 signed in url
    fetchS3SignedURLRequestPayload = {}
    fetchS3SignedURLRequestPayload['file_type'] = "file/octet-stream"
    fetchS3SignedURLRequestPayload['file_name'] = "uploads/file_upload/file_name/"+uuidValue+"/"+fileName
    S3URLRequestData = json.dumps(fetchS3SignedURLRequestPayload)
    fetchS3SignedURLResponsePayload = requests.post(bpy.types.Scene.functionalBaseURL[1]['default']+"/get_s3_signed_url",data = S3URLRequestData)
    S3URLResponseData = json.loads(fetchS3SignedURLResponsePayload.content)

    print("SUCCESS:: Fetch S3 Signin URL")

    ## Uploading .glb file on S3 bucket
    uploadFileRequestHeader = {'Content-Type': 'file/octet-stream','Access-Control-Allow-Origin': '*'}
    with open(filepath, "rb") as a_file:
        files = {'file': a_file}
        values = {'file_name': fileName}
        readFile = a_file.read()
        response = requests.put(S3URLResponseData['signed_url'],data = readFile,headers= uploadFileRequestHeader)
    print("SUCCESS:: Uploading Completed")

    ## Update agile version details in db
    fileType = 'GLB'
    updateAgileVersionEndPointHeader = {'authorization': bpy.context.scene.token,'Access-Control-Allow-Origin': '*'}
    updateVersionRequestPayload = 'mutation m{updateThreedModel(agileVersion:{agile_version_id:"' + bpy.context.scene.selectedAgileVersionId + '",threedModel:[{type:' + fileType + ',name:"' + fileName + '",uuid:"' + uuidValue + '"}]}),{agile_version_id}}';

    udpateVersionResponsePayload = requests.post(bpy.types.Scene.coreBaseURL[1]['default'],data = updateVersionRequestPayload,headers= updateAgileVersionEndPointHeader)
    updateVersionResponseData = json.loads(udpateVersionResponsePayload.content)

    ## reset value
    bpy.context.scene.selectedAgileVersionId = ""
    bpy.context.scene.name = ""
    bpy.context.scene.isAgileVersionSelected = False
    bpy.context.scene.isProcessRunning = False;

    print("SUCCESS:: Agile Version Updated")

    ## Invoke/Call operation complete popup
    bpy.ops.message.display('INVOKE_DEFAULT',message = "File Exporting Completed and Upload Finished.")
    return {'FINISHED'}


# ExportHelper is a helper class, defines filename and
# invoke() function which calls the file selector.


class ExportSomeData(Operator, ExportHelper):
    """This appears in the tooltip of the operator and in the generated docs"""
    bl_idname = "export_test.some_data"  # important since its how bpy.ops.import_test.some_data is constructed
    bl_label = "Export Some Data"

    # ExportHelper mixin class uses this
    filename_ext = ".glb"

    filter_glob: StringProperty(
        default="*.glb",
        options={'HIDDEN'},
        maxlen=255,  # Max internal buffer length, longer would be clamped.
    )

    # List of operator properties, the attributes will be assigned
    # to the class instance from the operator settings before calling.
    use_setting: BoolProperty(
        name="Example Boolean",
        description="Example Tooltip",
        default=True,
    )

    def execute(self, context):
        bpy.context.scene.isProcessRunning = True
        return write_some_data(context, self.filepath, self.use_setting)


# Only needed if you want to add into a dynamic menu
def menu_func_export(self, context):
    if context.scene.isAgileVersionSelected == True:
        self.layout.operator(ExportSomeData.bl_idname, text="Swivel Export")
    else:
        ShowMessageBox("Please Select Agile Version First...",title="Error", icon='ERROR')


## In this operator call login end-point and
## Fetch agile view list
class LoginActionOperator (Operator):
    bl_idname = "swivel.login"
    bl_label = "Login"

    def execute(self, context):
        bpy.context.scene.isProcessRunning = True;
        scene = context.scene
        request = scene.loginPropertyGroupTools
        if request['email']:
            if request['password']:
                email = request['email']
                passwordDecoded = request['password']
                passwordBytes = passwordDecoded.encode('utf-8')
                password = base64.b64encode(passwordBytes)
                passwordFinal = password.decode('utf-8')
                ## Login endpoint
                logInRequestPayload = 'mutation m{authenticateUser(user:{email:"'+email+'",password:"'+passwordFinal+'"}){message,result}}';
                logInResponsePayload = requests.post(bpy.types.Scene.authBaseURL[1]['default'],data = logInRequestPayload)
                logInResponseData = json.loads(logInResponsePayload.content)
                try:
                    print("SUCCESS:: Login")
                    bpy.context.scene.token = logInResponseData["data"]["authenticateUser"]["message"]
                    loggedInResult = logInResponseData["data"]["authenticateUser"]["result"]
                    bpy.context.scene.isAgileViewLoaded = True;

                    ## Fetch agile-view endpoint
                    fetchAgileViewsEndPointHeader = {'authorization': bpy.context.scene.token,'Access-Control-Allow-Origin': '*'}
                    fetchAgileViewsRequestPayload = "query{listAgileViews{agileview_id,url_name}}";

                    fetchAgileViewsResponsePayload = requests.post(bpy.types.Scene.coreBaseURL[1]['default'],data = fetchAgileViewsRequestPayload,headers= fetchAgileViewsEndPointHeader)
                    fetchAgileViewsResponseData = json.loads(fetchAgileViewsResponsePayload.content)
                    agileViewList = fetchAgileViewsResponseData["data"]["listAgileViews"]

                    if agileViewList:
                        print("SUCCESS:: Fetch Agile View List")
                        bpy.types.Scene.agileViewList = agileViewList
                    else:
                        print("WARNING:: Agile View List Is Null")
                    bpy.context.scene.isProcessRunning = False;
                except Exception:
                    print("ERROR:: Fetch Agile View List")
                    ShowMessageBox("Invalid Credentials!", title="Error", icon='ERROR')
                    bpy.context.scene.agileViewList = []
                    bpy.context.scene.isAgileViewLoaded = False;
                    bpy.context.scene.selectedAgileVersionId = ""
                    bpy.context.scene.selectedAgileViewId = ""
                    bpy.context.scene.selectedAgileVersionName = ""
                    bpy.context.scene.selectedAgileViewName = ""
                    bpy.context.scene.name = ""
                    bpy.context.scene.isAgileVersionSelected = False
                    bpy.context.scene.isProcessRunning = False;

            else:
                print("Password should not be blank")
                ShowMessageBox("Password should not be blank", title="Password", icon='ERROR')
        else:
            print("Email should not be blank")
            ShowMessageBox("Email should not be blank", title="Email", icon='ERROR')
        return {'FINISHED'}

## Define requried login parameters email, password
class LoginPropertyGroup(PropertyGroup):
    email: bpy.props.StringProperty(name="Email", default="", maxlen=1024)
    password: bpy.props.StringProperty(name="Password", default="", maxlen=1024, subtype='PASSWORD')


## This operator use for fetch agile version and store response
class FetchVersionsOperator(bpy.types.Operator):
    '''Select View'''
    bl_idname = "fetch.version"
    bl_label = "Button Operator"
    view_id = bpy.props.StringProperty(default='')

    def execute(self, context):
        bpy.types.Scene.versionEnumList = []
        bpy.types.Scene.versionList = []

        bpy.types.Scene.selectedAgileViewId = self.view_id

        ## Call fetch agile versions base on agile-view-id endpoint
        fetchVerisonsEndPointHeader = {'authorization': bpy.context.scene.token,'Access-Control-Allow-Origin': '*'}
        fetchVersionsRequestPayload = 'query{listAgileVersionByAgileViewId(agileview_id:"'+self.view_id+'"){agile_version_id,agileview_id,name}}';
        fetchVersionResponsePayload = requests.post(bpy.types.Scene.coreBaseURL[1]['default'],data = fetchVersionsRequestPayload,headers= fetchVerisonsEndPointHeader)
        responseVersions = json.loads(fetchVersionResponsePayload.content)
        versionList = responseVersions["data"]["listAgileVersionByAgileViewId"]

        if versionList:
            print("SUCCESS:: Fetch Agile Version List")
            bpy.types.Scene.versionList = versionList
        else:
            print("WARNING:: Agile Version List Is Null")

        ## If agile versions exist then store into versionList in tuple format(this use for enum property in dropdown)
        if versionList:
            bpy.types.Scene.versionEnumList = [(vobj['agile_version_id'],vobj['name'],vobj['name']) for vobj in versionList]
        else:
            bpy.types.Scene.versionEnumList = [('NULL','Version Not Created','Version Not Created')]

        ## Invoke/Call agile versions dropdown (VersionSelectionPopupOperator)
        bpy.ops.version.selector('INVOKE_DEFAULT')
        return {'FINISHED'}

## Return agile versions in enum type
def my_callback(scene,context):
    return bpy.types.Scene.versionEnumList

## Define Enum property for agile version
class VersionEnumPropertyGroup(PropertyGroup):

    objs = EnumProperty(
        name="Objects",
        description="",
        items=my_callback
        )

## This operator works as popup of agile versions
class VersionSelectionPopupOperator(bpy.types.Operator):
    '''The message operator. When invoked, print the given message in header.'''
    bl_idname = "version.selector"
    bl_label = "Select Agile Version"
    message = bpy.props.StringProperty(default='')
    preset_enum = VersionEnumPropertyGroup.objs

    ## Execute call once done selection on specific version from dropdown
    ## Store selected agile-version-id
    ## Change isAgileVersionSelected to True
    def execute(self, context):
        if self.preset_enum != 'NULL':
            bpy.context.scene.selectedAgileVersionId = self.preset_enum
            bpy.context.scene.isAgileVersionSelected = True

            ## Set agile version name and scene name
            versionIndex = next((index for (index, d) in enumerate(bpy.types.Scene.versionList) if d["agile_version_id"] == self.preset_enum), None)
            if versionIndex > -1:
                bpy.types.Scene.selectedAgileVersionName = bpy.types.Scene.versionList[versionIndex]['name']
                bpy.context.scene.name = bpy.types.Scene.versionList[versionIndex]['name']

            ## Set agile view name
            viewIndex = next((index for (index, d) in enumerate(bpy.types.Scene.agileViewList) if d["agileview_id"] == bpy.types.Scene.selectedAgileViewId), None)
            if viewIndex > -1:
                bpy.types.Scene.selectedAgileViewName = bpy.types.Scene.agileViewList[viewIndex]['url_name']

        self.report({'INFO'}, self.preset_enum)
        return {'FINISHED'}

    ## Invoke use for open popup
    def invoke(self, context, event):
        wm = context.window_manager
        return wm.invoke_props_dialog(self)

    ## Draw use for create inner layout in popup
    def draw(self, context):
        layout = self.layout
        layout.prop(self, "preset_enum")

## Popup for diplay info
class MessageOperator(bpy.types.Operator):
    '''Display Export File Status'''
    bl_idname = "message.display"
    bl_label = "AgileView Status"
    message = bpy.props.StringProperty(default='Export File on S3')

    def execute(self, context):
        return {'FINISHED'}

    def invoke(self, context, event):
        wm = context.window_manager
        return wm.invoke_props_dialog(self)

    ## Draw use for create inner layout in popup
    def draw(self, context):
        layout = self.layout
        box = layout.box()
        row = box.row()
        row.label(text="Status : "+ self.message)


## Login panel use for display login UI layout in modifier properties
class LoginLayoutPanel(Panel):
    bl_idname = "SCENE_PT_layout"
    bl_label = "Swivel Login Panel"
    bl_category = "Swivel Addon"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "modifier"

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        ## Custom logo label
        layout.label(text="SWIVEL", icon_value=custom_icons["custom_icon"].icon_id)

        rowEmail = layout.row()
        loginPropertyGroupTools = context.scene.loginPropertyGroupTools
        rowEmail.prop(loginPropertyGroupTools, "email")

        rowPassword = layout.row()
        loginPropertyGroupTools = context.scene.loginPropertyGroupTools
        rowPassword.prop(loginPropertyGroupTools, "password")

        rowLoginButton = layout.row()
        loginPropertyGroupTools = context.scene.loginPropertyGroupTools
        rowLoginButton.operator(LoginActionOperator.bl_idname)

        if scene.isProcessRunning == True:
            ## Loading lable
            layout.label(text="Loading >> >> >> >>", icon='PROP_ON')

        if scene.selectedAgileVersionId:
            layout.label(text="Selected View    : " + scene.selectedAgileViewName)
            layout.label(text="Selected Version : " + scene.selectedAgileVersionName)

            ## Export Operator
            rowExport = layout.row()
            rowExport.operator(ExportSomeData.bl_idname,text="Swivel Export", icon='EXPORT')
        if scene.isAgileViewLoaded == True:
            layout.label(text="Please Select Agile View")
            for viewObj in bpy.types.Scene.agileViewList:
                if viewObj['url_name']:
                    rowFit = layout.row()
                    rowFit.operator(FetchVersionsOperator.bl_idname,text=viewObj['url_name'], icon='MOD_BUILD').view_id = viewObj['agileview_id']
classes = (
           LoginActionOperator,
           LoginPropertyGroup,
           LoginLayoutPanel,
           ExportSomeData,
           VersionSelectionPopupOperator,
           FetchVersionsOperator,
           VersionEnumPropertyGroup,
           MessageOperator

           )
class DemoPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__
    # addon updater preferences from `__init__`, be sure to copy all of them
    auto_check_update = bpy.props.BoolProperty(
        name = "Auto-check for Update",
        description = "If enabled, auto-check for updates using an interval",
        default = False,
    )

    updater_intrval_months = bpy.props.IntProperty(
        name='Months',
        description = "Number of months between checking for updates",
        default=0,
        min=0
    )
    updater_intrval_days = bpy.props.IntProperty(
        name='Days',
        description = "Number of days between checking for updates",
        default=7,
        min=0,
    )
    updater_intrval_hours = bpy.props.IntProperty(
        name='Hours',
        description = "Number of hours between checking for updates",
        default=0,
        min=0,
        max=23
    )
    updater_intrval_minutes = bpy.props.IntProperty(
        name='Minutes',
        description = "Number of minutes between checking for updates",
        default=0,
        min=0,
        max=59
    )
    def draw(self, context):
        layout = self.layout
        addon_updater_ops.update_settings_ui(self, context)

def register():
    addon_updater_ops.register(bl_info)
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.loginPropertyGroupTools = bpy.props.PointerProperty(type=LoginPropertyGroup)
    bpy.types.Scene.versionEnumPropertyGroupTools = bpy.props.PointerProperty(type=VersionEnumPropertyGroup)
    bpy.types.Scene.isAgileViewLoaded = bpy.props.BoolProperty(name="Is Agile View Loaded", default=False)
    bpy.types.Scene.isAgileVersionSelected = bpy.props.BoolProperty(name="Is Agile Version Selected", default=False)
    bpy.types.Scene.selectedAgileVersionId = bpy.props.StringProperty(name="Selected VersionId", default="")
    bpy.types.Scene.selectedAgileViewId = bpy.props.StringProperty(name="Selected ViewId", default="")
    bpy.types.Scene.selectedAgileVersionName = bpy.props.StringProperty(name="Selected VersionName", default="")
    bpy.types.Scene.selectedAgileViewName = bpy.props.StringProperty(name="Selected ViewName", default="")
    bpy.types.Scene.token = bpy.props.StringProperty(name="token", default="")
    bpy.types.Scene.coreBaseURL = bpy.props.StringProperty(name="core API Base URL", default="https://api-dev-swivel.com/core/query")
    bpy.types.Scene.functionalBaseURL = bpy.props.StringProperty(name="functional API Base URL", default="https://api-dev-swivel.com/functional")
    bpy.types.Scene.authBaseURL = bpy.props.StringProperty(name="auth API Base URL", default="https://api-dev-swivel.com/auth/query")
    bpy.types.Scene.agileViewList = []
    bpy.types.Scene.versionEnumList = []
    bpy.types.Scene.versionList = []
    bpy.types.Scene.isProcessRunning = bpy.props.BoolProperty(name="Is Process Running", default=False)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)
    global custom_icons
    custom_icons = bpy.utils.previews.new()
    bpy.utils.register_class(DemoPreferences)
    ## Use following custom icon path while run script locally
    # script_path = bpy.context.space_data.text.filepath
    # icons_dir = os.path.join(os.path.dirname(script_path), "icons")
    custom_icons.load("custom_icon", os.path.join(icons_dir, "swivel-icon.png"), 'IMAGE')


def unregister():
    for cls in classes:
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.loginPropertyGroupTools
    del bpy.types.Scene.versionEnumPropertyGroupTools
    del bpy.types.Scene.isAgileViewLoaded
    del bpy.types.Scene.isAgileVersionSelected
    del bpy.types.Scene.selectedAgileVersionId
    del bpy.types.Scene.selectedAgileViewId
    del bpy.types.Scene.selectedAgileVersionName
    del bpy.types.Scene.selectedAgileViewName
    del bpy.types.Scene.token
    del bpy.types.Scene.coreBaseURL
    del bpy.types.Scene.functionalBaseURL
    del bpy.types.Scene.authBaseURL
    del bpy.types.Scene.agileViewList
    del bpy.types.Scene.versionEnumList
    del bpy.types.Scene.versionList
    del bpy.types.Scene.isProcessRunning
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)
    global custom_icons
    bpy.utils.previews.remove(custom_icons)
    bpy.utils.unregister_class(DemoPreferences)

if __name__ == "__main__":
    register()
