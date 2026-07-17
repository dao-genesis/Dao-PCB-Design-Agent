# 嘉立创EDA Pro EXTAPI 完整能力参考

> 一次性全量逆流·一劳永逸。自 `api-types.d.ts`（TypeScript 声明，权威）解析，与运行期 `_EXTAPI_ROOT_` introspection 交叉核对 live 可达性。
>
> - API 版本：`0.2.53.aee2f57a`　生成：`2026-07-17`
> - 命名空间 **95** 个，可直接 RPC 调用方法 **749** 个；返回/数据类型 **31** 个（链式方法 766 个）。
> - 词汇：枚举 **69** 个、接口 **128** 个、类型别名 **30** 个（见文末「词汇表」，含层 id/图元类型/库类型等取值）。
> - 根映射：`EDA` 根类把每个命名空间以「类名首段小写」暴露（`PCB_Drc`→`pcb_Drc`），经源码核实。
> - 调用：`driver._call('<namespace>.<method>', *args)`（见 `dao_rpc_driver.py`）。

## 模块索引

- **DMT · 工程/编辑器/团队/工作区** — 11 命名空间 / 86 方法
- **LIB · 元件库（器件/封装/符号/3D/立创商城）** — 9 命名空间 / 65 方法
- **PCB · 印制板（图元/层/网络/DRC/制造/3D）** — 25 命名空间 / 278 方法
- **SCH · 原理图（图元/网络/网表/DRC/仿真/制造）** — 22 命名空间 / 161 方法
- **PNL · 拼板** — 1 命名空间 / 1 方法
- **SYS · 系统（文件/对话框/存储/环境/消息/窗口/单位…）** — 26 命名空间 / 158 方法
- **EDA · 根对象** — 1 命名空间 / 0 方法

## DMT · 工程/编辑器/团队/工作区

### `dmt_Board` · DMT_Board （live 可达 7/7）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `createBoard` | `createBoard(schematicUuid?: string, pcbUuid?: string): Promise<string \| undefined>` | 创建板子 | ✓ |
| `modifyBoardName` | `modifyBoardName(originalBoardName: string, boardName: string): Promise<boolean>` | 修改板子名称 | ✓ |
| `copyBoard` | `copyBoard(sourceBoardName: string): Promise<string \| undefined>` | 复制板子 | ✓ |
| `getBoardInfo` | `getBoardInfo(boardName: string): Promise<IDMT_BoardItem \| undefined>` | 获取板子的详细属性 | ✓ |
| `getAllBoardsInfo` | `getAllBoardsInfo(): Promise<Array<IDMT_BoardItem>>` | 获取工程内所有板子的详细属性 | ✓ |
| `getCurrentBoardInfo` | `getCurrentBoardInfo(): Promise<IDMT_BoardItem \| undefined>` | 获取当前板子的详细属性 | ✓ |
| `deleteBoard` | `deleteBoard(boardName: string): Promise<boolean>` | 删除板子 | ✓ |

### `dmt_EditorControl` · DMT_EditorControl （live 可达 19/19）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `openDocument` | `openDocument(documentUuid: string, splitScreenId?: string): Promise<string \| undefined>` | 打开文档 | ✓ |
| `openLibraryDocument` | `openLibraryDocument(libraryUuid: string, libraryType: ELIB_LibraryType.SYMBOL \| ELIB_LibraryType.FOOTPRINT, uuid: string, splitScreenId?: string): Promise<string \| undefined>` | 打开库符号、封装文档 | ✓ |
| `closeDocument` | `closeDocument(tabId: string): Promise<boolean>` | 关闭文档 | ✓ |
| `getSplitScreenTree` | `getSplitScreenTree(): Promise<IDMT_EditorSplitScreenItem \| undefined>` | 获取编辑器分屏属性树 | ✓ |
| `getSplitScreenIdByTabId` | `getSplitScreenIdByTabId(tabId: string): Promise<string \| undefined>` | 使用标签页 ID 获取分屏 ID | ✓ |
| `getTabsBySplitScreenId` | `getTabsBySplitScreenId(splitScreenId: string): Promise<Array<IDMT_EditorTabItem>>` | 获取指定分屏 ID 下的所有标签页 | ✓ |
| `createSplitScreen` | `createSplitScreen(splitScreenType: EDMT_EditorSplitScreenDirection, tabId: string): Promise<{ sourceSplitScreenId: string; newSplitScreenId: string; } \| undefined>` | 创建分屏 | ✓ |
| `moveDocumentToSplitScreen` | `moveDocumentToSplitScreen(tabId: string, splitScreenId: string): Promise<boolean>` | 将文档移动到指定分屏 | ✓ |
| `activateDocument` | `activateDocument(tabId: string): Promise<boolean>` | 激活文档 | ✓ |
| `activateSplitScreen` | `activateSplitScreen(splitScreenId: string): Promise<boolean>` | 激活分屏 | ✓ |
| `tileAllDocumentToSplitScreen` | `tileAllDocumentToSplitScreen(): Promise<boolean>` | 平铺所有文档 | ✓ |
| `mergeAllDocumentFromSplitScreen` | `mergeAllDocumentFromSplitScreen(): Promise<boolean>` | 合并所有分屏 | ✓ |
| `getCurrentRenderedAreaImage` | `getCurrentRenderedAreaImage(tabId?: string): Promise<Blob \| undefined>` | 获取画布渲染区域图像 | ✓ |
| `zoomToRegion` | `zoomToRegion(left: number, right: number, top: number, bottom: number, tabId?: string): Promise<boolean>` | 缩放到区域 | ✓ |
| `zoomTo` | `zoomTo(x?: number, y?: number, scaleRatio?: number, tabId?: string): Promise<{ left: number; right: number; top: number; bottom: number; } \| false>` | 缩放到坐标 | ✓ |
| `zoomToAllPrimitives` | `zoomToAllPrimitives(tabId?: string): Promise<{ left: number; right: number; top: number; bottom: number; } \| false>` | 缩放到所有图元（适应全部） | ✓ |
| `zoomToSelectedPrimitives` | `zoomToSelectedPrimitives(tabId?: string): Promise<{ left: number; right: number; top: number; bottom: number; } \| false>` | 缩放到已选中图元（适应选中） | ✓ |
| `generateIndicatorMarkers` | `generateIndicatorMarkers(markers: Array<IDMT_IndicatorMarkerShape>, color?: { r: number; g: number; b: number; alpha: number; }, lineWidth?: number, zoom?: boolean, tabId?: string): Promise<boolean>` | 生成指示标记 | ✓ |
| `removeIndicatorMarkers` | `removeIndicatorMarkers(tabId?: string): Promise<boolean>` | 移除指示标记 | ✓ |

### `dmt_Event` · DMT_Event （live 可达 3/3）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `addEditorTabEventListener` | `addEditorTabEventListener(id: string, eventType: 'all' \| EDMT_EditorTabEventType, callFn: (eventType: EDMT_EditorTabEventType, props: { documentType: EDMT_EditorDocumentType; title: string; tabId: string; }) => void \| Promise<void>, onlyOnce?: boolean): void` | 新增编辑器标签页事件监听 | ✓ |
| `removeEventListener` | `removeEventListener(id: string): boolean` | 移除事件监听 | ✓ |
| `isEventListenerAlreadyExist` | `isEventListenerAlreadyExist(id: string): boolean` | 查询事件监听是否存在 | ✓ |

### `dmt_Folder` · DMT_Folder （live 可达 7/7）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `createFolder` | `createFolder(folderName: string, teamUuid: string, parentFolderUuid?: string, description?: string): Promise<string \| undefined>` | 创建文件夹 | ✓ |
| `modifyFolderName` | `modifyFolderName(teamUuid: string, folderUuid: string, folderName: string): Promise<boolean>` | 修改文件夹名称 | ✓ |
| `modifyFolderDescription` | `modifyFolderDescription(teamUuid: string, folderUuid: string, description?: string): Promise<boolean>` | 修改文件夹描述 | ✓ |
| `moveFolderToFolder` | `moveFolderToFolder(teamUuid: string, folderUuid: string, parentFolderUuid?: string): Promise<boolean>` | 移动文件夹 | ✓ |
| `getAllFoldersUuid` | `getAllFoldersUuid(teamUuid: string): Promise<Array<string>>` | 获取所有文件夹的 UUID | ✓ |
| `getFolderInfo` | `getFolderInfo(teamUuid: string, folderUuid: string): Promise<IDMT_FolderItem \| undefined>` | 获取文件夹详细属性 | ✓ |
| `deleteFolder` | `deleteFolder(teamUuid: string, folderUuid: string): Promise<boolean>` | 删除文件夹 | ✓ |

### `dmt_Panel` · DMT_Panel （live 可达 7/7）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `createPanel` | `createPanel(): Promise<string \| undefined>` | 创建面板 | ✓ |
| `modifyPanelName` | `modifyPanelName(panelUuid: string, panelName: string): Promise<boolean>` | 修改面板名称 | ✓ |
| `copyPanel` | `copyPanel(panelUuid: string): Promise<string \| undefined>` | 复制面板 | ✓ |
| `getPanelInfo` | `getPanelInfo(panelUuid: string): Promise<IDMT_PanelItem \| undefined>` | 获取面板的详细属性 | ✓ |
| `getAllPanelsInfo` | `getAllPanelsInfo(): Promise<Array<IDMT_PanelItem>>` | 获取工程内所有面板的详细属性 | ✓ |
| `getCurrentPanelInfo` | `getCurrentPanelInfo(): Promise<IDMT_PanelItem \| undefined>` | 获取当前面板的详细属性 | ✓ |
| `deletePanel` | `deletePanel(panelUuid: string): Promise<boolean>` | 删除面板 | ✓ |

### `dmt_Pcb` · DMT_Pcb （live 可达 7/7）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `createPcb` | `createPcb(boardName?: string): Promise<string \| undefined>` | 创建 PCB | ✓ |
| `modifyPcbName` | `modifyPcbName(pcbUuid: string, pcbName: string): Promise<boolean>` | 修改 PCB 名称 | ✓ |
| `copyPcb` | `copyPcb(pcbUuid: string, boardName?: string): Promise<string \| undefined>` | 复制 PCB | ✓ |
| `getPcbInfo` | `getPcbInfo(pcbUuid: string): Promise<IDMT_PcbItem \| undefined>` | 获取 PCB 的详细属性 | ✓ |
| `getAllPcbsInfo` | `getAllPcbsInfo(): Promise<Array<IDMT_PcbItem>>` | 获取工程内所有 PCB 的详细属性 | ✓ |
| `getCurrentPcbInfo` | `getCurrentPcbInfo(): Promise<IDMT_PcbItem \| undefined>` | 获取当前 PCB 的详细属性 | ✓ |
| `deletePcb` | `deletePcb(pcbUuid: string): Promise<boolean>` | 删除 PCB | ✓ |

### `dmt_Project` · DMT_Project （live 可达 12/12）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `openProject` | `openProject(projectUuid: string): Promise<boolean>` | 打开工程 | ✓ |
| `createProject` | `createProject(projectFriendlyName: string, projectName?: string, teamUuid?: string, folderUuid?: string, description?: string, collaborationMode?: EDMT_ProjectCollaborationMode): Promise<string \| undefined>` | 创建工程 | ✓ |
| `modifyProjectFriendlyName` | `modifyProjectFriendlyName(projectUuid: string, projectFriendlyName: string): boolean` | 修改工程友好名称 | ✓ |
| `modifyProjectDescription` | `modifyProjectDescription(projectUuid: string, description?: string): boolean` | 修改工程描述 | ✓ |
| `modifyProjectCollaborationMode` | `modifyProjectCollaborationMode(projectUuid: string, collaborationMode: EDMT_ProjectCollaborationMode): boolean` | 修改工程协作模式 | ✓ |
| `moveProject` | `moveProject(projectUuid: string, teamUuid: string, folderUuid?: string): boolean` | 移动工程 | ✓ |
| `moveProjectToFolder` | `moveProjectToFolder(projectUuid: string, folderUuid?: string): Promise<boolean>` | 移动工程到文件夹 | ✓ |
| `copyProject` | `copyProject(sourceProjectUuid: string, targetTeamUuid?: string, targetFolderUuid?: string, newProjectFriendlyName?: string, newProjectName?: string): string \| undefined` | 复制工程 | ✓ |
| `getAllProjectsUuid` | `getAllProjectsUuid(teamUuid?: string, folderUuid?: string, workspaceUuid?: string): Promise<Array<string>>` | 获取所有工程的 UUID | ✓ |
| `getProjectInfo` | `getProjectInfo(projectUuid: string): Promise<IDMT_BriefProjectItem \| undefined>` | 获取工程属性 | ✓ |
| `getCurrentProjectInfo` | `getCurrentProjectInfo(): Promise<IDMT_ProjectItem \| undefined>` | 获取当前工程的详细属性 | ✓ |
| `deleteProject` | `deleteProject(projectUuid: string): boolean` | 删除工程 | ✓ |

### `dmt_Schematic` · DMT_Schematic （live 可达 17/17）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `createSchematic` | `createSchematic(boardName?: string): Promise<string \| undefined>` | 创建原理图 | ✓ |
| `createSchematicPage` | `createSchematicPage(schematicUuid: string): Promise<string \| undefined>` | 创建原理图图页 | ✓ |
| `modifySchematicName` | `modifySchematicName(schematicUuid: string, schematicName: string): Promise<boolean>` | 修改原理图名称 | ✓ |
| `modifySchematicPageName` | `modifySchematicPageName(schematicPageUuid: string, schematicPageName: string): Promise<boolean>` | 修改原理图图页名称 | ✓ |
| `modifySchematicPageTitleBlock` | `modifySchematicPageTitleBlock(showTitleBlock?: boolean, titleBlockData?: { [key: string]: { showTitle?: boolean; showValue?: boolean; value?: any; }; }): Promise<boolean>` | 修改原理图图页明细表 | ✓ |
| `copySchematic` | `copySchematic(schematicUuid: string, boardName?: string): Promise<string \| undefined>` | 复制原理图 | ✓ |
| `copySchematicPage` | `copySchematicPage(schematicPageUuid: string, schematicUuid?: string): Promise<string \| undefined>` | 复制原理图图页 | ✓ |
| `getSchematicInfo` | `getSchematicInfo(schematicUuid: string): Promise<IDMT_SchematicItem \| undefined>` | 获取原理图的详细属性 | ✓ |
| `getSchematicPageInfo` | `getSchematicPageInfo(schematicPageUuid: string): Promise<IDMT_SchematicPageItem \| undefined>` | 获取原理图图页的详细属性 | ✓ |
| `getAllSchematicsInfo` | `getAllSchematicsInfo(): Promise<Array<IDMT_SchematicItem>>` | 获取工程内所有原理图的详细属性 | ✓ |
| `getAllSchematicPagesInfo` | `getAllSchematicPagesInfo(): Promise<Array<IDMT_SchematicPageItem>>` | 获取工程内所有原理图图页的详细属性 | ✓ |
| `getCurrentSchematicAllSchematicPagesInfo` | `getCurrentSchematicAllSchematicPagesInfo(): Promise<Array<IDMT_SchematicPageItem>>` | 获取当前原理图内所有原理图图页的详细属性 | ✓ |
| `getCurrentSchematicInfo` | `getCurrentSchematicInfo(): Promise<IDMT_SchematicItem \| undefined>` | 获取当前原理图的详细属性 | ✓ |
| `getCurrentSchematicPageInfo` | `getCurrentSchematicPageInfo(): Promise<IDMT_SchematicPageItem \| undefined>` | 获取当前原理图图页的详细属性 | ✓ |
| `reorderSchematicPages` | `reorderSchematicPages(schematicUuid: string, schematicPageItemsArray: Array<IDMT_SchematicPageItem>): Promise<boolean>` | 重新排序原理图图页 | ✓ |
| `deleteSchematic` | `deleteSchematic(schematicUuid: string): Promise<boolean>` | 删除原理图 | ✓ |
| `deleteSchematicPage` | `deleteSchematicPage(schematicPageUuid: string): Promise<boolean>` | 删除原理图图页 | ✓ |

### `dmt_SelectControl` · DMT_SelectControl （live 可达 1/1）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `getCurrentDocumentInfo` | `getCurrentDocumentInfo(): Promise<IDMT_EditorDocumentItem \| undefined>` | 获取当前文档的属性 | ✓ |

### `dmt_Team` · DMT_Team （live 可达 3/3）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `getAllTeamsInfo` | `getAllTeamsInfo(): Promise<Array<IDMT_TeamItem>>` | 获取所有直接团队的详细属性 | ✓ |
| `getAllInvolvedTeamInfo` | `getAllInvolvedTeamInfo(): Promise<Array<IDMT_TeamItem>>` | 获取所有参与的团队的详细属性 | ✓ |
| `getCurrentTeamInfo` | `getCurrentTeamInfo(): Promise<IDMT_TeamItem \| undefined>` | 获取当前团队的详细属性 | ✓ |

### `dmt_Workspace` · DMT_Workspace （live 可达 3/3）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `getAllWorkspacesInfo` | `getAllWorkspacesInfo(): Promise<Array<IDMT_WorkspaceItem>>` | 获取所有工作区的详细属性 | ✓ |
| `toggleToWorkspace` | `toggleToWorkspace(workspaceUuid?: string): Promise<boolean>` | 切换到工作区 | ✓ |
| `getCurrentWorkspaceInfo` | `getCurrentWorkspaceInfo(): Promise<IDMT_WorkspaceItem \| undefined>` | 获取当前工作区的详细属性 | ✓ |

## LIB · 元件库（器件/封装/符号/3D/立创商城）

### `lib_3DModel` · LIB_3DModel （live 可达 6/6）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `create` | `create(libraryUuid: string, modelFile: Blob, classification?: ILIB_ClassificationIndex \| Array<string>, unit?: ESYS_Unit.MILLIMETER \| ESYS_Unit.CENTIMETER \| ESYS_Unit.METER \| ESYS_Unit.MIL \| ESYS_Unit.INCH): Promise<string[] \| undefined>` | 创建 3D 模型 | ✓ |
| `delete` | `delete(modelUuid: string, libraryUuid: string): Promise<boolean>` | 删除 3D 模型 | ✓ |
| `modify` | `modify(modelUuid: string, libraryUuid: string, modelName?: string, classification?: ILIB_ClassificationIndex \| Array<string> \| null, description?: string \| null): Promise<boolean>` | 修改 3D 模型 | ✓ |
| `get` | `get(modelUuid: string, libraryUuid?: string): Promise<ILIB_3DModelItem \| undefined>` | 获取 3D 模型的所有属性 | ✓ |
| `copy` | `copy(modelUuid: string, libraryUuid: string, targetLibraryUuid: string, targetClassification?: ILIB_ClassificationIndex \| Array<string>, newModelName?: string): Promise<string \| undefined>` | 复制 3D 模型 | ✓ |
| `search` | `search(key: string, libraryUuid?: string, classification?: ILIB_ClassificationIndex \| Array<string>, itemsOfPage?: number, page?: number): Promise<Array<ILIB_3DModelSearchItem>>` | 搜索 3D 模型 | ✓ |

### `lib_Cbb` · LIB_Cbb （live 可达 8/8）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `create` | `create(libraryUuid: string, cbbName: string, classification?: ILIB_ClassificationIndex \| Array<string>, description?: string): Promise<string \| undefined>` | 创建复用模块 | ✓ |
| `delete` | `delete(cbbUuid: string, libraryUuid: string): Promise<boolean>` | 删除复用模块 | ✓ |
| `modify` | `modify(cbbUuid: string, libraryUuid: string, cbbName?: string, classification?: ILIB_ClassificationIndex \| Array<string> \| null, description?: string \| null): Promise<boolean>` | 修改复用模块 | ✓ |
| `get` | `get(cbbUuid: string, libraryUuid?: string): Promise<ILIB_CbbItem \| undefined>` | 获取复用模块的所有属性 | ✓ |
| `copy` | `copy(cbbUuid: string, libraryUuid: string, targetLibraryUuid: string, targetClassification?: ILIB_ClassificationIndex \| Array<string>, newCbbName?: string): Promise<string \| undefined>` | 复制复用模块 | ✓ |
| `search` | `search(key: string, libraryUuid?: string, classification?: ILIB_ClassificationIndex \| Array<string>, itemsOfPage?: number, page?: number): Promise<Array<ILIB_CbbSearchItem>>` | 搜索复用模块 | ✓ |
| `openProjectInEditor` | `openProjectInEditor(cbbUuid: string, libraryUuid: string): Promise<boolean>` | 在编辑器打开复用模块工程 | ✓ |
| `openSymbolInEditor` | `openSymbolInEditor(cbbUuid: string, libraryUuid: string, splitScreenId?: string): Promise<string \| undefined>` | 在编辑器打开复用模块符号 | ✓ |

### `lib_Classification` · LIB_Classification （live 可达 8/8）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `createPrimary` | `createPrimary(libraryUuid: string, libraryType: ELIB_LibraryType, primaryClassificationName: string): Promise<ILIB_ClassificationIndex \| undefined>` | 创建一级分类 | ✓ |
| `createSecondary` | `createSecondary(libraryUuid: string, libraryType: ELIB_LibraryType, primaryClassificationUuid: string, secondaryClassificationName: string): Promise<ILIB_ClassificationIndex \| undefined>` | 创建二级分类 | ✓ |
| `getIndexByName` | `getIndexByName(libraryUuid: string, libraryType: ELIB_LibraryType, primaryClassificationName: string, secondaryClassificationName?: string): Promise<ILIB_ClassificationIndex \| undefined>` | 获取指定名称的分类的分类索引 | ✓ |
| `getNameByUuid` | `getNameByUuid(libraryUuid: string, libraryType: ELIB_LibraryType, primaryClassificationUuid: string, secondaryClassificationUuid?: string): Promise<{ primaryClassificationName: string; secondaryClassificationName?: string \| undefined; } \| undefined>` | 获取指定 UUID 的分类的名称 | ✓ |
| `getNameByIndex` | `getNameByIndex(classificationIndex: ILIB_ClassificationIndex): Promise<{ primaryClassificationName: string; secondaryClassificationName?: string \| undefined; } \| undefined>` | 获取指定索引的分类的名称 | ✓ |
| `getAllClassificationTree` | `getAllClassificationTree(libraryUuid: string, libraryType: ELIB_LibraryType): Promise<Array<{ name: string; uuid: string; children?: Array<{ name: string; uuid: string; }> \| undefined; }>>` | 获取所有分类信息组成的树 | ✓ |
| `deleteByUuid` | `deleteByUuid(libraryUuid: string, classificationUuid: string): Promise<boolean>` | 删除指定 UUID 的分类 | ✓ |
| `deleteByIndex` | `deleteByIndex(classificationIndex: ILIB_ClassificationIndex): Promise<boolean>` | 删除指定索引的分类 | ✓ |

### `lib_Device` · LIB_Device （live 可达 9/9）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `create` | `create(libraryUuid: string, deviceName: string, classification?: ILIB_ClassificationIndex \| Array<string>, association?: { symbolType?: ELIB_SymbolType; symbolUuid?: string; symbol?: { uuid: string; libraryUuid: string; }; footprintUuid?: string; footprint?: { uuid: string; libraryUuid: string; }; model3D?: { uuid: string; libraryUuid: string; }; imageData?: File \| Blob; }, description?: string, property?: ILIB_DeviceExtendPropertyItem): Promise<string \| undefined>` | 创建器件 | ✓ |
| `delete` | `delete(deviceUuid: string, libraryUuid: string): Promise<boolean>` | 删除器件 | ✓ |
| `modify` | `modify(deviceUuid: string, libraryUuid: string, deviceName?: string, classification?: ILIB_ClassificationIndex \| Array<string> \| null, association?: { symbolUuid?: string; symbol?: { uuid: string; libraryUuid: string; }; footprintUuid?: string \| null; footprint?: { uuid: string; libraryUuid: string; } \| null; model3D?: { uuid: string; libraryUuid: string; } \| null; imageData?: File \| Blob \| null; }, description?: string \| null, property?: { name?: string \| null; designator?: string; addIntoBom?: boolean; addIntoPcb?: boolean; net?: string; manufacturer?: string \| null; manufacturerId?: string \| null; supplier?: string \| null; supplierId?: string \| null; otherProperty?: { [key: string]: boolean \| number \| string \| undefined \| null; }; }): Promise<boolean>` | 修改器件 | ✓ |
| `get` | `get(deviceUuid: string, libraryUuid?: string): Promise<ILIB_DeviceItem \| undefined>` | 获取器件的所有属性 | ✓ |
| `copy` | `copy(deviceUuid: string, libraryUuid: string, targetLibraryUuid: string, targetClassification?: ILIB_ClassificationIndex \| Array<string>, newDeviceName?: string): Promise<string \| undefined>` | 复制器件 | ✓ |
| `search` | `search(key: string, libraryUuid?: string, classification?: ILIB_ClassificationIndex \| Array<string>, symbolType?: ELIB_SymbolType, itemsOfPage?: number, page?: number): Promise<Array<ILIB_DeviceSearchItem>>` | 搜索器件 | ✓ |
| `searchByProperties` | `searchByProperties(properties: ILIB_DevicePropertiesForSearch, libraryUuid?: string, classification?: Array<string>, symbolType?: ELIB_SymbolType, itemsOfPage?: number, page?: number): Promise<Array<ILIB_DeviceSearchItem>>` | 使用属性精确搜索器件 | ✓ |
| `getByLcscIds` | `getByLcscIds<T extends boolean>(lcscIds: string, libraryUuid?: string, allowMultiMatch?: T): Promise<T extends true ? ILIB_DeviceSearchItem \| undefined : Array<ILIB_DeviceSearchItem>>` | 使用立创 C 编号获取器件 | ✓ |
| `getByLcscIds` | `getByLcscIds(lcscIds: Array<string>, libraryUuid?: string, allowMultiMatch?: boolean): Promise<Array<ILIB_DeviceSearchItem>>` | 使用立创 C 编号批量获取器件 | ✓ |

### `lib_Footprint` · LIB_Footprint （live 可达 10/10）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `create` | `create(libraryUuid: string, footprintName: string, classification?: ILIB_ClassificationIndex \| Array<string>, description?: string): Promise<string \| undefined>` | 创建封装 | ✓ |
| `delete` | `delete(footprintUuid: string, libraryUuid: string): Promise<boolean>` | 删除封装 | ✓ |
| `modify` | `modify(footprintUuid: string, libraryUuid: string, footprintName?: string, classification?: ILIB_ClassificationIndex \| Array<string> \| null, description?: string \| null): Promise<boolean>` | 修改封装 | ✓ |
| `updateDocumentSource` | `updateDocumentSource(footprintUuid: string, libraryUuid: string, documentSource: string): Promise<boolean \| undefined>` | 更新封装的文档源码 | ✓ |
| `get` | `get(footprintUuid: string, libraryUuid?: string): Promise<ILIB_FootprintItem \| undefined>` | 获取封装的所有属性 | ✓ |
| `copy` | `copy(footprintUuid: string, libraryUuid: string, targetLibraryUuid: string, targetClassification?: ILIB_ClassificationIndex \| Array<string>, newFootprintName?: string): Promise<string \| undefined>` | 复制封装 | ✓ |
| `search` | `search(key: string, libraryUuid?: string, classification?: ILIB_ClassificationIndex \| Array<string>, itemsOfPage?: number, page?: number): Promise<Array<ILIB_FootprintSearchItem>>` | 搜索封装 | ✓ |
| `searchByProperties` | `searchByProperties(properties: ILIB_FootprintPropertiesForSearch, libraryUuid?: string): Promise<Array<ILIB_FootprintSearchItem>>` | 使用属性精确搜索封装 | ✓ |
| `openInEditor` | `openInEditor(footprintUuid: string, libraryUuid: string, splitScreenId?: string): Promise<string \| undefined>` | 在编辑器打开文档 | ✓ |
| `getRenderImage` | `getRenderImage(source: { footprintUuid: string; libraryUuid: string; }): Promise<Blob \| undefined>` | 获取封装渲染图 | ✓ |

### `lib_LibrariesList` · LIB_LibrariesList （live 可达 6/6）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `getSystemLibraryUuid` | `getSystemLibraryUuid(): Promise<string \| undefined>` | 获取系统库的 UUID | ✓ |
| `getPersonalLibraryUuid` | `getPersonalLibraryUuid(): Promise<string \| undefined>` | 获取个人库的 UUID | ✓ |
| `getProjectLibraryUuid` | `getProjectLibraryUuid(): Promise<string \| undefined>` | 获取工程库的 UUID | ✓ |
| `getFavoriteLibraryUuid` | `getFavoriteLibraryUuid(): Promise<string \| undefined>` | 获取收藏库的 UUID | ✓ |
| `getAllLibrariesList` | `getAllLibrariesList(): Promise<Array<ILIB_LibraryInfo>>` | 获取所有库的列表 | ✓ |
| `registerExtendLibrary` | `registerExtendLibrary(title: string, libraryFunctions: { device?: ILIB_ExtendLibraryDeviceFunctions; symbol?: ILIB_ExtendLibrarySymbolFunctions; footprint?: ILIB_ExtendLibraryFootprintFunctions; cbb?: ILIB_ExtendLibraryCbbFunctions; model3d?: ILIB_ExtendLibrary3DModelFunctions; }): Promise<string \| undefined>` | 注册外部库 | ✓ |

### `lib_PanelLibrary` · LIB_PanelLibrary （live 可达 7/7）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `create` | `create(libraryUuid: string, panelLibraryName: string, classification?: ILIB_ClassificationIndex \| Array<string>, description?: string): Promise<string \| undefined>` | 创建面板库 | ✓ |
| `delete` | `delete(panelLibraryUuid: string, libraryUuid: string): Promise<boolean>` | 删除面板库 | ✓ |
| `modify` | `modify(panelLibraryUuid: string, libraryUuid: string, panelLibraryName?: string, classification?: ILIB_ClassificationIndex \| Array<string> \| null, description?: string \| null): Promise<boolean>` | 修改面板库 | ✓ |
| `get` | `get(panelLibraryUuid: string, libraryUuid?: string): Promise<ILIB_PanelLibraryItem \| undefined>` | 获取面板库的所有属性 | ✓ |
| `copy` | `copy(panelLibraryUuid: string, libraryUuid: string, targetLibraryUuid: string, targetClassification?: ILIB_ClassificationIndex \| Array<string>, newPanelLibraryName?: string): Promise<string \| undefined>` | 复制面板库 | ✓ |
| `search` | `search(key: string, libraryUuid?: string, classification?: ILIB_ClassificationIndex \| Array<string>, itemsOfPage?: number, page?: number): Promise<Array<ILIB_PanelLibrarySearchItem>>` | 搜索面板库 | ✓ |
| `openInEditor` | `openInEditor(panelLibraryUuid: string, libraryUuid: string, splitScreenId?: string): Promise<string \| undefined>` | 在编辑器打开文档 | ✓ |

### `lib_SelectControl` · LIB_SelectControl （live 可达 1/1）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `getSelectedLibraryRowInfo` | `getSelectedLibraryRowInfo(): Promise<ILIB_LibraryItem \| undefined>` | 获取当前底部库选中行的信息 | ✓ |

### `lib_Symbol` · LIB_Symbol （live 可达 10/10）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `create` | `create(libraryUuid: string, symbolName: string, classification?: ILIB_ClassificationIndex \| Array<string>, symbolType?: ELIB_SymbolType, description?: string): Promise<string \| undefined>` | 创建符号 | ✓ |
| `delete` | `delete(symbolUuid: string, libraryUuid: string): Promise<boolean>` | 删除符号 | ✓ |
| `modify` | `modify(symbolUuid: string, libraryUuid: string, symbolName?: string, classification?: ILIB_ClassificationIndex \| Array<string> \| null, description?: string \| null): Promise<boolean>` | 修改符号 | ✓ |
| `updateDocumentSource` | `updateDocumentSource(symbolUuid: string, libraryUuid: string, documentSource: string): Promise<boolean \| undefined>` | 更新符号的文档源码 | ✓ |
| `get` | `get(symbolUuid: string, libraryUuid?: string): Promise<ILIB_SymbolItem \| undefined>` | 获取符号的所有属性 | ✓ |
| `copy` | `copy(symbolUuid: string, libraryUuid: string, targetLibraryUuid: string, targetClassification?: ILIB_ClassificationIndex \| Array<string>, newSymbolName?: string): Promise<string \| undefined>` | 复制符号 | ✓ |
| `search` | `search(key: string, libraryUuid?: string, classification?: ILIB_ClassificationIndex \| Array<string>, symbolType?: ELIB_SymbolType, itemsOfPage?: number, page?: number): Promise<Array<ILIB_SymbolSearchItem>>` | 搜索符号 | ✓ |
| `searchByProperties` | `searchByProperties(properties: ILIB_SymbolPropertiesForSearch, libraryUuid?: string): Promise<Array<ILIB_SymbolSearchItem>>` | 使用属性精确搜索符号 | ✓ |
| `openInEditor` | `openInEditor(symbolUuid: string, libraryUuid: string, splitScreenId?: string): Promise<string \| undefined>` | 在编辑器打开文档 | ✓ |
| `getRenderImage` | `getRenderImage(source: { symbolUuid: string; libraryUuid: string; subPartName?: string; }): Promise<Blob \| undefined>` | 获取符号渲染图 | ✓ |

## PCB · 印制板（图元/层/网络/DRC/制造/3D）

### `pcb_Document` · PCB_Document （live 可达 19/19）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `importChanges` | `importChanges(uuid?: string): Promise<boolean>` | 从原理图导入变更 | ✓ |
| `importAutoRouteJsonFile` | `importAutoRouteJsonFile(autoRouteFile: File): Promise<boolean>` | 导入自动布线文件（JSON） | ✓ |
| `importAutoRouteSesFile` | `importAutoRouteSesFile(autoRouteFile: File): Promise<boolean>` | 导入自动布线文件（SES） | ✓ |
| `importAutoLayoutJsonFile` | `importAutoLayoutJsonFile(autoLayoutFile: File): Promise<boolean>` | 导入自动布局文件（JSON） | ✓ |
| `save` | `save(uuid: string): Promise<boolean>` | 保存文档 | ✓ |
| `getCalculatingRatlineStatus` | `getCalculatingRatlineStatus(): Promise<EPCB_DocumentRatlineCalculatingActiveStatus>` | 获取当前飞线计算功能状态 | ✓ |
| `startCalculatingRatline` | `startCalculatingRatline(): Promise<boolean>` | 启动飞线计算功能 | ✓ |
| `stopCalculatingRatline` | `stopCalculatingRatline(): Promise<boolean>` | 停止飞线计算功能 | ✓ |
| `convertCanvasOriginToDataOrigin` | `convertCanvasOriginToDataOrigin(x: number, y: number): Promise<{ x: number; y: number; }>` | 输入画布坐标返回该坐标对应的数据坐标 | ✓ |
| `convertDataOriginToCanvasOrigin` | `convertDataOriginToCanvasOrigin(x: number, y: number): Promise<{ x: number; y: number; }>` | 输入数据坐标返回该坐标对应的画布坐标 | ✓ |
| `getCanvasOrigin` | `getCanvasOrigin(): Promise<{ offsetX: number; offsetY: number; }>` | 获取画布原点相对于数据原点的偏移坐标 | ✓ |
| `setCanvasOrigin` | `setCanvasOrigin(offsetX: number, offsetY: number): Promise<boolean>` | 设置画布原点相对于数据原点的偏移坐标 | ✓ |
| `navigateToCoordinates` | `navigateToCoordinates(x: number, y: number): Promise<boolean>` | 定位到画布坐标 | ✓ |
| `navigateToRegion` | `navigateToRegion(left: number, right: number, top: number, bottom: number): Promise<boolean>` | 定位到画布区域 | ✓ |
| `getPrimitiveAtPoint` | `getPrimitiveAtPoint(x: number, y: number): Promise<IPCB_Primitive \| undefined>` | 获取坐标点的图元 | ✓ |
| `getPrimitivesInRegion` | `getPrimitivesInRegion(left: number, right: number, top: number, bottom: number, leftToRight?: boolean): Promise<Array<IPCB_Primitive>>` | 获取区域内所有图元 | ✓ |
| `zoomToBoardOutline` | `zoomToBoardOutline(): Promise<boolean>` | 缩放到板框（适应板框） | ✓ |
| `getCurrentFilterConfiguration` | `getCurrentFilterConfiguration(): Promise<{ [key: string]: any; } \| undefined>` | 获取当前画布过滤器配置 | ✓ |
| `clearRouting` | `clearRouting(type?: 'all' \| 'net' \| 'connection'): Promise<boolean>` | 清除布线 | ✓ |

### `pcb_Drc` · PCB_Drc （live 可达 46/46）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `check` | `check(strict: boolean, userInterface: boolean, includeVerboseError: false): Promise<boolean>` | 检查 DRC | ✓ |
| `check` | `check(strict: boolean, userInterface: boolean, includeVerboseError: true): Promise<Array<any>>` | 检查 DRC | ✓ |
| `getRealTimeDrcStatus` | `getRealTimeDrcStatus(): boolean` | 获取实时 DRC 检查状态 | ✓ |
| `startRealTimeDrc` | `startRealTimeDrc(): boolean` | 开始实时 DRC 检查 | ✓ |
| `stopRealTimeDrc` | `stopRealTimeDrc(): boolean` | 停止实时 DRC 检查 | ✓ |
| `getCurrentRuleConfigurationName` | `getCurrentRuleConfigurationName(): Promise<string \| undefined>` | 获取当前设计规则配置名称 | ✓ |
| `getCurrentRuleConfiguration` | `getCurrentRuleConfiguration(): Promise<{ [key: string]: any; } \| undefined>` | 获取当前设计规则配置 | ✓ |
| `getRuleConfiguration` | `getRuleConfiguration(configurationName: string): Promise<{ [key: string]: any; } \| undefined>` | 获取指定设计规则配置 | ✓ |
| `getAllRuleConfigurations` | `getAllRuleConfigurations(includeSystem?: boolean): Promise<Array<{ [key: string]: any; }>>` | 获取所有设计规则配置 | ✓ |
| `saveRuleConfiguration` | `saveRuleConfiguration(ruleConfiguration: { [key: string]: any; }, configurationName: string, allowOverwrite?: boolean): Promise<boolean>` | 保存设计规则配置 | ✓ |
| `renameRuleConfiguration` | `renameRuleConfiguration(originalConfigurationName: string, configurationName: string): Promise<boolean>` | 重命名设计规则配置 | ✓ |
| `deleteRuleConfiguration` | `deleteRuleConfiguration(configurationName: string): Promise<boolean>` | 删除设计规则配置 | ✓ |
| `getDefaultRuleConfigurationName` | `getDefaultRuleConfigurationName(): Promise<string \| undefined>` | 获取新建 PCB 默认设计规则配置的名称 | ✓ |
| `setAsDefaultRuleConfiguration` | `setAsDefaultRuleConfiguration(configurationName: string): Promise<boolean>` | 设置为新建 PCB 默认设计规则配置 | ✓ |
| `overwriteCurrentRuleConfiguration` | `overwriteCurrentRuleConfiguration(ruleConfiguration: { [key: string]: any; }): Promise<boolean>` | 覆写当前设计规则配置 | ✓ |
| `getNetRules` | `getNetRules(): Promise<Array<{ [key: string]: any; }>>` | 获取网络规则 | ✓ |
| `overwriteNetRules` | `overwriteNetRules(netRules: Array<{ [key: string]: any; }>): Promise<boolean>` | 覆写网络规则 | ✓ |
| `getNetByNetRules` | `getNetByNetRules(): Promise<{ [key: string]: any; }>` | 获取网络-网络规则 | ✓ |
| `overwriteNetByNetRules` | `overwriteNetByNetRules(netByNetRules: { [key: string]: any; }): Promise<boolean>` | 覆写网络-网络规则 | ✓ |
| `getRegionRules` | `getRegionRules(): Promise<Array<{ [key: string]: any; }>>` | 获取区域规则 | ✓ |
| `overwriteRegionRules` | `overwriteRegionRules(regionRules: Array<{ [key: string]: any; }>): Promise<boolean>` | 覆写区域规则 | ✓ |
| `createNetClass` | `createNetClass(netClassName: string, nets: Array<string>, color: IPCB_EqualLengthNetGroupItem['color']): Promise<boolean>` | 创建网络类 | ✓ |
| `deleteNetClass` | `deleteNetClass(netClassName: string): Promise<boolean>` | 删除网络类 | ✓ |
| `modifyNetClassName` | `modifyNetClassName(originalNetClassName: string, netClassName: string): Promise<boolean>` | 修改网络类的名称 | ✓ |
| `addNetToNetClass` | `addNetToNetClass(netClassName: string, net: string \| Array<string>): Promise<boolean>` | 将网络添加到网络类 | ✓ |
| `removeNetFromNetClass` | `removeNetFromNetClass(netClassName: string, net: string \| Array<string>): Promise<boolean>` | 从网络类中移除网络 | ✓ |
| `getAllNetClasses` | `getAllNetClasses(): Promise<Array<IPCB_NetClassItem>>` | 获取所有网络类的详细属性 | ✓ |
| `createDifferentialPair` | `createDifferentialPair(differentialPairName: string, positiveNet: string, negativeNet: string): Promise<boolean>` | 创建差分对 | ✓ |
| `deleteDifferentialPair` | `deleteDifferentialPair(differentialPairName: string): Promise<boolean>` | 删除差分对 | ✓ |
| `modifyDifferentialPairName` | `modifyDifferentialPairName(originalDifferentialPairName: string, differentialPairName: string): Promise<boolean>` | 修改差分对的名称 | ✓ |
| `modifyDifferentialPairPositiveNet` | `modifyDifferentialPairPositiveNet(differentialPairName: string, positiveNet: string): Promise<boolean>` | 修改差分对正网络 | ✓ |
| `modifyDifferentialPairNegativeNet` | `modifyDifferentialPairNegativeNet(differentialPairName: string, negativeNet: string): Promise<boolean>` | 修改差分对负网络 | ✓ |
| `getAllDifferentialPairs` | `getAllDifferentialPairs(): Promise<Array<IPCB_DifferentialPairItem> \| { [key: string]: any; }>` | 获取所有差分对的详细属性 | ✓ |
| `createEqualLengthNetGroup` | `createEqualLengthNetGroup(equalLengthNetGroupName: string, nets: Array<string>, color: IPCB_EqualLengthNetGroupItem['color']): Promise<boolean>` | 创建等长网络组 | ✓ |
| `deleteEqualLengthNetGroup` | `deleteEqualLengthNetGroup(equalLengthNetGroupName: string): Promise<boolean>` | 删除等长网络组 | ✓ |
| `modifyEqualLengthNetGroupName` | `modifyEqualLengthNetGroupName(originalEqualLengthNetGroupName: string, equalLengthNetGroupName: string): Promise<boolean>` | 修改等长网络组的名称 | ✓ |
| `addNetToEqualLengthNetGroup` | `addNetToEqualLengthNetGroup(equalLengthNetGroupName: string, net: string \| Array<string>): Promise<boolean>` | 将网络添加到等长网络组 | ✓ |
| `removeNetFromEqualLengthNetGroup` | `removeNetFromEqualLengthNetGroup(equalLengthNetGroupName: string, net: string \| Array<string>): Promise<boolean>` | 从等长网络组中移除网络 | ✓ |
| `getAllEqualLengthNetGroups` | `getAllEqualLengthNetGroups(): Promise<Array<IPCB_EqualLengthNetGroupItem>>` | 获取所有等长网络组的详细属性 | ✓ |
| `createPadPairGroup` | `createPadPairGroup(padPairGroupName: string, padPairs: Array<[string, string]>): Promise<boolean>` | 创建焊盘对组 | ✓ |
| `deletePadPairGroup` | `deletePadPairGroup(padPairGroupName: string): Promise<boolean>` | 删除焊盘对组 | ✓ |
| `modifyPadPairGroupName` | `modifyPadPairGroupName(originalPadPairGroupName: string, padPairGroupName: string): Promise<boolean>` | 修改焊盘对组的名称 | ✓ |
| `addPadPairToPadPairGroup` | `addPadPairToPadPairGroup(padPairGroupName: string, padPair: [string, string] \| Array<[string, string]>): Promise<boolean>` | 将焊盘对添加到焊盘对组 | ✓ |
| `removePadPairFromPadPairGroup` | `removePadPairFromPadPairGroup(padPairGroupName: string, padPair: [string, string] \| Array<[string, string]>): Promise<boolean>` | 从焊盘对组中移除焊盘对 | ✓ |
| `getAllPadPairGroups` | `getAllPadPairGroups(): Promise<Array<IPCB_PadPairGroupItem>>` | 获取所有焊盘对组的详细属性 | ✓ |
| `getPadPairGroupMinWireLength` | `getPadPairGroupMinWireLength(padPairGroupName: string): Promise<Array<IPCB_PadPairMinWireLengthItem>>` | 获取焊盘对组最短导线长度 | ✓ |

### `pcb_Event` · PCB_Event （live 可达 7/7）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `addMouseEventListener` | `addMouseEventListener(id: string, eventType: 'all' \| EPCB_MouseEventType, callFn: (eventType: EPCB_MouseEventType, props: [ { primitiveId: string; primitiveType: EPCB_PrimitiveType; net?: string; designator?: string; parentComponentPrimitiveId?: string; parentComponentDesignator?: string; } ]) => void \| Promise<void>, onlyOnce?: boolean): void` | 新增鼠标事件监听 | ✓ |
| `addPrimitiveEventListener` | `addPrimitiveEventListener(id: string, eventType: 'all' \| EPCB_PrimitiveEventType, callFn: (eventType: EPCB_PrimitiveEventType, props: [ { primitiveId: string; primitiveType: EPCB_PrimitiveType; net?: string; designator?: string; parentComponentPrimitiveId?: string; parentComponentDesignator?: string; } ]) => void \| Promise<void>, onlyOnce?: boolean): void` | 新增图元事件监听 | ✓ |
| `addNetEventListener` | `addNetEventListener(id: string, eventType: 'all' \| EPCB_NetEventType, callFn: (eventType: EPCB_NetEventType, props: [{ net: string; }]) => void \| Promise<void>, onlyOnce?: boolean): void` | 新增网络事件监听 | ✓ |
| `addCrossProbeSelectEventListener` | `addCrossProbeSelectEventListener(id: string, callFn: (props: any) => void \| Promise<void>): void` | 新增交叉选择事件监听 | ✓ |
| `addRealTimeDrcResultEventListener` | `addRealTimeDrcResultEventListener(id: string, eventType: 'all', callFn: (eventType: undefined, props: [{ drcResult: any; }]) => void \| Promise<void>): void` | 新增实时 DRC 结果事件监听 | ✓ |
| `removeEventListener` | `removeEventListener(id: string): boolean` | 移除事件监听 | ✓ |
| `isEventListenerAlreadyExist` | `isEventListenerAlreadyExist(id: string): boolean` | 查询事件监听是否存在 | ✓ |

### `pcb_Layer` · PCB_Layer （live 可达 26/26）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `getCurrentLayer` | `getCurrentLayer(): IPCB_LayerItem \| undefined` | 获取当前图层的详细属性 | ✓ |
| `selectLayer` | `selectLayer(layer: TPCB_LayersInTheSelectable): Promise<boolean>` | 选中图层 | ✓ |
| `setLayerVisible` | `setLayerVisible(layer?: TPCB_LayersInTheSelectable \| Array<TPCB_LayersInTheSelectable>, setOtherLayerInvisible?: boolean): Promise<boolean>` | 将层设置为可见 | ✓ |
| `setLayerInvisible` | `setLayerInvisible(layer?: TPCB_LayersInTheSelectable \| Array<TPCB_LayersInTheSelectable>, setOtherLayerVisible?: boolean): Promise<boolean>` | 将层设置为不可见 | ✓ |
| `lockLayer` | `lockLayer(layer?: TPCB_LayersInTheSelectable \| Array<TPCB_LayersInTheSelectable>): Promise<boolean>` | 锁定层 | ✓ |
| `unlockLayer` | `unlockLayer(layer?: TPCB_LayersInTheSelectable \| Array<TPCB_LayersInTheSelectable>): Promise<boolean>` | 取消锁定层 | ✓ |
| `setTheNumberOfCopperLayers` | `setTheNumberOfCopperLayers(numberOfLayers: 2 \| 4 \| 6 \| 8 \| 10 \| 12 \| 14 \| 16 \| 18 \| 20 \| 22 \| 24 \| 26 \| 28 \| 30 \| 32): Promise<boolean>` | 设置铜箔层数 | ✓ |
| `getTheNumberOfCopperLayers` | `getTheNumberOfCopperLayers(): Promise<number>` | 获取铜箔层数 | ✓ |
| `setLayerColorConfiguration` | `setLayerColorConfiguration(colorConfiguration: EPCB_LayerColorConfiguration): Promise<boolean>` | 设置层颜色配置 | ✓ |
| `setInactiveLayerTransparency` | `setInactiveLayerTransparency(transparency: number): Promise<boolean>` | 设置非激活层透明度 | ✓ |
| `setPcbType` | `setPcbType(pcbType: EPCB_PcbPlateType): Promise<boolean>` | 设置 PCB 类型 | ✓ |
| `addCustomLayer` | `addCustomLayer(): Promise<TPCB_LayersOfCustom \| undefined>` | 新增自定义层 | ✓ |
| `removeLayer` | `removeLayer(layer: TPCB_LayersOfCustom): Promise<boolean>` | 移除层 | ✓ |
| `modifyLayer` | `modifyLayer(layer: TPCB_LayersInTheSelectable, property: { name?: string; type?: TPCB_LayerTypesOfInnerLayer; color?: string; transparency?: number; }): Promise<boolean>` | 修改图层属性 | ✓ |
| `getAllLayers` | `getAllLayers(): Promise<Array<IPCB_LayerItem>>` | 获取所有图层的详细属性 | ✓ |
| `setInactiveLayerDisplayMode` | `setInactiveLayerDisplayMode(displayMode?: EPCB_InactiveLayerDisplayMode): Promise<boolean>` | 设置非激活层展示模式 | ✓ |
| `getCurrentPhysicalStackingConfigurationName` | `getCurrentPhysicalStackingConfigurationName(): Promise<string \| undefined>` | 获取当前物理叠层配置名称 | ✓ |
| `getCurrentPhysicalStackingConfiguration` | `getCurrentPhysicalStackingConfiguration(): { [key: string]: any; } \| undefined` | 获取当前物理叠层配置 | ✓ |
| `getPhysicalStackingConfiguration` | `getPhysicalStackingConfiguration(configurationName: string): Promise<{ [key: string]: any; } \| undefined>` | 获取指定物理叠层配置 | ✓ |
| `getAllPhysicalStackingConfigurations` | `getAllPhysicalStackingConfigurations(): Promise<Array<{ [key: string]: any; }>>` | 获取所有物理叠层配置 | ✓ |
| `savePhysicalStackingConfiguration` | `savePhysicalStackingConfiguration(physicalStackingConfiguration: { [key: string]: any; }, configurationName: string, allowOverwrite?: boolean): Promise<boolean>` | 保存物理叠层配置 | ✓ |
| `renamePhysicalStackingConfiguration` | `renamePhysicalStackingConfiguration(originalConfigurationName: string, configurationName: string): Promise<boolean>` | 重命名物理叠层配置 | ✓ |
| `deletePhysicalStackingConfiguration` | `deletePhysicalStackingConfiguration(configurationName: string): Promise<boolean>` | 删除物理叠层配置 | ✓ |
| `getDefaultPhysicalStackingConfigurationName` | `getDefaultPhysicalStackingConfigurationName(): Promise<string \| undefined>` | 获取新建 PCB 默认物理叠层配置的名称 | ✓ |
| `setAsDefaultPhysicalStackingConfiguration` | `setAsDefaultPhysicalStackingConfiguration(configurationName: string): Promise<boolean>` | 设置为新建 PCB 默认物理叠层配置 | ✓ |
| `overwriteCurrentPhysicalStackingConfiguration` | `overwriteCurrentPhysicalStackingConfiguration(physicalStackingConfiguration: { [key: string]: any; }): boolean` | 覆写当前物理叠层配置 | ✓ |

### `pcb_ManufactureData` · PCB_ManufactureData （live 可达 31/31）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `getGerberFile` | `getGerberFile(fileName?: string, colorSilkscreen?: boolean, unit?: ESYS_Unit.MILLIMETER \| ESYS_Unit.INCH, digitalFormat?: { integerNumber: number; decimalNumber: number; }, other?: { metallicDrillingInformation: boolean; nonMetallicDrillingInformation: boolean; drillTable: boolean; flyingProbeTestingFile: boolean; }, layers?: Array<{ layerId: number; isMirror: boolean; }>, objects?: Array<'Pad' \| 'Via' \| 'Track' \| 'Text' \| 'Image' \| 'Dimension' \| 'BoardOutline' \| 'BoardCutout' \| 'CopperFilled' \| 'SolidRegion' \| 'FPCStiffener' \| 'Line' \| 'PlaneZone' \| 'ComponentProperty' \| 'ComponentSilkscreen' \| 'TearDrop'>): Promise<File \| undefined>` | 获取 PCB 制版文件（Gerber） | ✓ |
| `get3DFile` | `get3DFile(fileName?: string, fileType?: 'step' \| 'obj', element?: Array<'Component Model' \| 'Via' \| 'Silkscreen' \| 'Wire In Signal Layer'>, modelMode?: 'Outfit' \| 'Parts', autoGenerateModels?: boolean): Promise<File \| undefined>` | 获取 3D 模型文件 | ✓ |
| `get3DShellFile` | `get3DShellFile(fileName?: string, fileType?: 'stl' \| 'step' \| 'obj'): Promise<File \| undefined>` | 获取 3D 外壳文件 | ✓ |
| `getPickAndPlaceFile` | `getPickAndPlaceFile(fileName?: string, fileType?: 'xlsx' \| 'csv', unit?: ESYS_Unit.MILLIMETER \| ESYS_Unit.MIL): Promise<File \| undefined>` | 获取坐标文件（PickAndPlace） | ✓ |
| `getFlyingProbeTestFile` | `getFlyingProbeTestFile(fileName?: string): Promise<File \| undefined>` | 获取飞针测试文件 | ✓ |
| `getBomTemplates` | `getBomTemplates(): Promise<Array<string>>` | 获取 BOM 模板列表 | ✓ |
| `uploadBomTemplateFile` | `uploadBomTemplateFile(templateFile: File, template?: string): Promise<string \| undefined>` | 上传 BOM 模板文件 | ✓ |
| `getBomTemplateFile` | `getBomTemplateFile(template: string): Promise<File \| undefined>` | 获取 BOM 模板文件 | ✓ |
| `deleteBomTemplate` | `deleteBomTemplate(template: string): Promise<boolean>` | 删除 BOM 模板 | ✓ |
| `getBomFile` | `getBomFile(fileName?: string, fileType?: 'xlsx' \| 'csv', template?: string, filterOptions?: Array<{ property: string; includeValue: boolean \| string; }>, statistics?: Array<string>, property?: Array<string>, columns?: Array<IPCB_BomPropertiesTableColumns>): Promise<File \| undefined>` | 获取 BOM 文件 | ✓ |
| `getTestPointFile` | `getTestPointFile(fileName?: string, fileType?: 'xlsx' \| 'csv'): Promise<File \| undefined>` | 获取测试点报告文件 | ✓ |
| `getNetlistFile` | `getNetlistFile(fileName?: string, netlistType?: ESYS_NetlistType): Promise<File \| undefined>` | 获取网表文件（Netlist） | ✓ |
| `getDxfFile` | `getDxfFile(fileName?: string, layers?: Array<{ layerId: number; mirror: boolean; }>, objects?: Array<string>): Promise<File \| undefined>` | 获取 DXF 文件 | ✓ |
| `getPdfFile` | `getPdfFile(fileName?: string, outputMethod?: EPCB_PdfOutputMethod, contentConfig?: { displayAttributesAsMenu: boolean; showOutlineOnly: boolean; }, watermark?: { show?: boolean; content?: string; styleConfig?: { color: string; transparency: 'Opaque' \| '75%' \| '50%' \| '25%'; font: string; fontSize: string; style: { blood: boolean; italic: boolean; underline: boolean; }; slope: 0 \| 45 \| 90; denseness: 'Single' \| 'Sparse' \| 'Std' \| 'Dense'; }; }, graphPageConfig?: Array<{ [key: string]: any; }>): Promise<File \| undefined>` | 获取 PDF 文件 | ✓ |
| `getIpcD356AFile` | `getIpcD356AFile(fileName?: string): Promise<File \| undefined>` | 获取 IPC-D-356A 文件 | ✓ |
| `getIpc2581CFile` | `getIpc2581CFile(fileName?: string, fileType?: 'xml' \| 'cvg' \| '2581', unit?: ESYS_Unit.INCH \| ESYS_Unit.MILLIMETER, oemNumber?: 'Device' \| 'Manufacturer Part' \| 'Supplier Part' \| 'Comment'): Promise<File \| undefined>` | 获取 IPC-2581C 文件 | ✓ |
| `getOpenDatabaseDoublePlusFile` | `getOpenDatabaseDoublePlusFile(fileName?: string, unit?: ESYS_Unit.INCH, otherData?: { metallizedDrilledHoles?: boolean; nonMetallizedDrilledHoles?: boolean; drillTable?: boolean; flyingProbeTestFile?: boolean; }, layers?: Array<{ layerId: number; mirror: boolean; }>, objects?: Array<{ objectName: string; }>): Promise<File \| undefined>` | 获取 ODB++ 文件 | ✓ |
| `getInteractiveBomFile` | `getInteractiveBomFile(fileName?: string): Promise<File \| undefined>` | 获取交互式 BOM 文件 | ✓ |
| `getDsnFile` | `getDsnFile(fileName?: string): Promise<File \| undefined>` | 获取自动布线文件（DSN） | ✓ |
| `getAutoRouteJsonFile` | `getAutoRouteJsonFile(fileName?: string): Promise<File \| undefined>` | 获取自动布线文件（JSON） | ✓ |
| `getAutoRouteJsonFileForJRouter` | `getAutoRouteJsonFileForJRouter(fileName?: string): Promise<File \| undefined>` | 获取 JRouter 专用自动布线文件（JSON） | ✓ |
| `getAutoLayoutJsonFile` | `getAutoLayoutJsonFile(fileName?: string): Promise<File \| undefined>` | 获取自动布局文件（JSON） | ✓ |
| `getAltiumDesignerFile` | `getAltiumDesignerFile(fileName?: string): Promise<File \| undefined>` | 获取 Altium Designer 文件 | ✓ |
| `getPadsFile` | `getPadsFile(fileName?: string): Promise<File \| undefined>` | 获取 PADS 文件 | ✓ |
| `getPcbInfoFile` | `getPcbInfoFile(fileName?: string): Promise<File \| undefined>` | 获取 PCB 信息文件 | ✓ |
| `getIdxFile` | `getIdxFile(fileName?: string): Promise<File \| undefined>` | 获取 IDX 文件 | ✓ |
| `placeComponentsOrder` | `placeComponentsOrder(interactive?: boolean, ignoreWarning?: boolean): Promise<boolean>` | 元件下单 | ✓ |
| `placeSmtComponentsOrder` | `placeSmtComponentsOrder(interactive?: boolean, ignoreWarning?: boolean): Promise<boolean>` | SMT 元件下单 | ✓ |
| `placePcbOrder` | `placePcbOrder(interactive?: boolean, ignoreWarning?: boolean): Promise<boolean>` | PCB 下单 | ✓ |
| `place3DShellOrder` | `place3DShellOrder(interactive?: boolean, ignoreWarning?: boolean): Promise<boolean>` | 3D 外壳下单 | ✓ |
| `getManufactureData` | `getManufactureData(): Promise<File \| undefined>` | 导出制造文件 | ✓ |

### `pcb_MathPolygon` · PCB_MathPolygon （live 可达 8/8）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `createPolygon` | `createPolygon(polygon: TPCB_PolygonSourceArray): IPCB_Polygon \| undefined` | 创建单多边形 | ✓ |
| `createComplexPolygon` | `createComplexPolygon(complexPolygon: TPCB_PolygonSourceArray \| Array<TPCB_PolygonSourceArray> \| IPCB_Polygon \| Array<IPCB_Polygon>): IPCB_ComplexPolygon \| undefined` | 创建复杂多边形 | ✓ |
| `splitPolygon` | `splitPolygon(...complexPolygons: Array<IPCB_ComplexPolygon>): Array<IPCB_Polygon>` | 拆分单多边形 | ✓ |
| `discretize` | `discretize(polygon: IPCB_Polygon \| TPCB_PolygonSourceArray, options?: IPCB_DiscretizeOptions): Array<IPCB_DiscretizedPoint>` | 将单多边形离散化为点数据 | ✓ |
| `calculateWidth` | `calculateWidth(complexPolygon: TPCB_PolygonSourceArray \| Array<TPCB_PolygonSourceArray> \| IPCB_Polygon \| IPCB_ComplexPolygon): number` | 计算复杂多边形 BBox 宽度 | ✓ |
| `calculateHeight` | `calculateHeight(complexPolygon: TPCB_PolygonSourceArray \| Array<TPCB_PolygonSourceArray> \| IPCB_Polygon \| IPCB_ComplexPolygon): number` | 计算复杂多边形 BBox 高度 | ✓ |
| `calculateBBoxHeight` | `calculateBBoxHeight(complexPolygon: TPCB_PolygonSourceArray \| Array<TPCB_PolygonSourceArray>): number` |  | ✓ |
| `convertImageToComplexPolygon` | `convertImageToComplexPolygon(imageBlob: Blob, imageWidth: number, imageHeight: number, tolerance?: number, simplification?: number, smoothing?: number, despeckling?: number, whiteAsBackgroundColor?: boolean, inversion?: boolean): Promise<IPCB_ComplexPolygon \| undefined>` | 将图像转换为复杂多边形对象 | ✓ |

### `pcb_Net` · PCB_Net （live 可达 16/16）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `getAllNets` | `getAllNets(): Promise<Array<IPCB_NetInfo>>` | 获取所有网络的详细信息 | ✓ |
| `getNet` | `getNet(net: string): Promise<IPCB_NetInfo \| undefined>` | 获取指定网络的详细信息 | ✓ |
| `getAllNetsName` | `getAllNetsName(): Promise<Array<string>>` | 获取所有网络的网络名称 | ✓ |
| `getAllNetName` | `getAllNetName(): Promise<Array<string>>` | 获取所有网络的网络名称 | ✓ |
| `getNetLength` | `getNetLength(net: string): Promise<number \| undefined>` | 获取指定网络的长度 | ✓ |
| `getNetColor` | `getNetColor(net: string): Promise<IPCB_NetInfo['color'] \| undefined>` | 获取指定网络的颜色 | ✓ |
| `setNetColor` | `setNetColor(net: string, color: IPCB_NetInfo['color']): Promise<boolean>` | 设置指定网络的颜色 | ✓ |
| `getAllPrimitivesByNet` | `getAllPrimitivesByNet(net: string, primitiveTypes?: Array<EPCB_PrimitiveType>): Promise<Array<IPCB_Primitive>>` | 获取关联指定网络的所有图元 | ✓ |
| `selectNet` | `selectNet(net: string): Promise<boolean>` | 选中网络 | ✓ |
| `unselectNet` | `unselectNet(net: string): Promise<boolean>` | 取消选中网络 | ✓ |
| `unselectAllNets` | `unselectAllNets(): Promise<boolean>` | 取消选中所有网络 | ✓ |
| `highlightNet` | `highlightNet(net: string): Promise<boolean>` | 高亮网络 | ✓ |
| `unhighlightNet` | `unhighlightNet(net: string): Promise<boolean>` | 取消高亮网络 | ✓ |
| `unhighlightAllNets` | `unhighlightAllNets(): Promise<boolean>` | 取消高亮所有网络 | ✓ |
| `getNetlist` | `getNetlist(type?: ESYS_NetlistType): Promise<string>` | 获取网表 | ✓ |
| `setNetlist` | `setNetlist(type: ESYS_NetlistType \| undefined, netlist: string): Promise<boolean>` | 更新网表 | ✓ |

### `pcb_Primitive` · PCB_Primitive （live 可达 5/5）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `getPrimitiveTypeByPrimitiveId` | `getPrimitiveTypeByPrimitiveId(id: string): Promise<EPCB_PrimitiveType \| undefined>` | 获取指定 ID 的图元的图元类型 | ✓ |
| `getPrimitiveByPrimitiveId` | `getPrimitiveByPrimitiveId(id: string): Promise<IPCB_Primitive \| undefined>` | 获取指定 ID 的图元的所有属性 | ✓ |
| `getPrimitivesByPrimitiveId` | `getPrimitivesByPrimitiveId(ids: Array<string>): Promise<Array<IPCB_Primitive>>` | 获取指定所有 ID 的图元的所有属性 | ✓ |
| `getPrimitivesBBox` | `getPrimitivesBBox(primitiveIds: Array<string \| IPCB_Primitive>): Promise<{ minX: number; minY: number; maxX: number; maxY: number; } \| undefined>` | 获取图元的 BBox | ✓ |
| `getPrimitiveBoardLine` | `getPrimitiveBoardLine(primitiveId: string, layers?: Array<EPCB_LayerId>): IPCB_ComplexPolygon \| undefined` | 获取图元的边框线 | ✓ |

### `pcb_PrimitiveArc` · PCB_PrimitiveArc （live 可达 7/7）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `create` | `create(net: string, layer: TPCB_LayersOfLine, startX: number, startY: number, endX: number, endY: number, arcAngle: number, lineWidth?: number, interactiveMode?: EPCB_PrimitiveArcInteractiveMode, primitiveLock?: boolean): Promise<IPCB_PrimitiveArc \| undefined>` | 创建圆弧线 | ✓ |
| `delete` | `delete(primitiveIds: string \| IPCB_PrimitiveArc \| Array<string> \| Array<IPCB_PrimitiveArc>): Promise<boolean>` | 删除圆弧线 | ✓ |
| `modify` | `modify(primitiveId: string \| IPCB_PrimitiveArc, property: { net?: string; layer?: TPCB_LayersOfLine; startX?: number; startY?: number; endX?: number; endY?: number; arcAngle?: number; lineWidth?: number; interactiveMode?: EPCB_PrimitiveArcInteractiveMode; primitiveLock?: boolean; }): Promise<IPCB_PrimitiveArc \| undefined>` | 修改圆弧线 | ✓ |
| `get` | `get(primitiveIds: string): Promise<IPCB_PrimitiveArc \| undefined>` | 获取圆弧线 | ✓ |
| `get` | `get(primitiveIds: Array<string>): Promise<Array<IPCB_PrimitiveArc>>` | 获取圆弧线 | ✓ |
| `getAllPrimitiveId` | `getAllPrimitiveId(net?: string, layer?: TPCB_LayersOfLine, primitiveLock?: boolean): Promise<Array<string>>` | 获取所有圆弧线的图元 ID | ✓ |
| `getAll` | `getAll(net?: string, layer?: TPCB_LayersOfLine, primitiveLock?: boolean): Promise<Array<IPCB_PrimitiveArc>>` | 获取所有圆弧线 | ✓ |

### `pcb_PrimitiveAttribute` · PCB_PrimitiveAttribute （live 可达 7/7）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `create` | `create(): undefined` | 创建属性 | ✓ |
| `delete` | `delete(primitiveIds: string \| IPCB_PrimitiveAttribute \| Array<string> \| Array<IPCB_PrimitiveAttribute>): Promise<boolean>` | 删除属性 | ✓ |
| `modify` | `modify(primitiveId: string \| IPCB_PrimitiveAttribute, property: { layer?: TPCB_LayersOfImage; x?: number; y?: number; key?: string; value?: string; keyVisible?: boolean; valueVisible?: boolean; fontFamily?: string; fontSize?: number; lineWidth?: number; alignMode?: EPCB_PrimitiveStringAlignMode; rotation?: number; reverse?: boolean; expansion?: number; mirror?: boolean; primitiveLock?: boolean; }): Promise<IPCB_PrimitiveAttribute \| undefined>` | 修改文本 | ✓ |
| `get` | `get(primitiveIds: string): Promise<IPCB_PrimitiveAttribute \| undefined>` | 获取属性 | ✓ |
| `get` | `get(primitiveIds: Array<string>): Promise<Array<IPCB_PrimitiveAttribute>>` | 获取属性 | ✓ |
| `getAllPrimitiveId` | `getAllPrimitiveId(parentPrimitiveId?: string, layer?: TPCB_LayersOfImage, primitiveLock?: boolean): Promise<Array<string>>` | 获取所有属性的图元 ID | ✓ |
| `getAll` | `getAll(parentPrimitiveId?: string, layer?: TPCB_LayersOfImage, primitiveLock?: boolean): Promise<Array<IPCB_PrimitiveAttribute>>` | 获取所有属性 | ✓ |

### `pcb_PrimitiveComponent` · PCB_PrimitiveComponent （live 可达 11/11）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `create` | `create(component: { libraryUuid: string; uuid: string; } \| ILIB_DeviceItem \| ILIB_DeviceSearchItem \| { libraryType: ELIB_LibraryType.FOOTPRINT; libraryUuid: string; uuid: string; } \| ILIB_FootprintItem \| ILIB_FootprintSearchItem, layer: TPCB_LayersOfComponent, x: number, y: number, rotation?: number, primitiveLock?: boolean): Promise<IPCB_PrimitiveComponent \| undefined>` | 创建器件 | ✓ |
| `delete` | `delete(primitiveIds: string \| IPCB_PrimitiveComponent \| Array<string> \| Array<IPCB_PrimitiveComponent>): Promise<boolean>` | 删除器件 | ✓ |
| `modify` | `modify(primitiveId: string \| IPCB_PrimitiveComponent, property: { layer?: TPCB_LayersOfComponent; x?: number; y?: number; rotation?: number; primitiveLock?: boolean; addIntoBom?: boolean; designator?: string \| null; name?: string \| null; uniqueId?: string \| null; manufacturer?: string \| null; manufacturerId?: string \| null; supplier?: string \| null; supplierId?: string \| null; otherProperty?: { [key: string]: any; }; }): Promise<IPCB_PrimitiveComponent \| undefined>` | 修改器件 | ✓ |
| `get` | `get(primitiveIds: string): Promise<IPCB_PrimitiveComponent \| undefined>` | 获取器件 | ✓ |
| `get` | `get(primitiveIds: Array<string>): Promise<Array<IPCB_PrimitiveComponent>>` | 获取器件 | ✓ |
| `getAllPrimitiveId` | `getAllPrimitiveId(layer?: TPCB_LayersOfComponent, primitiveLock?: boolean): Promise<Array<string>>` | 获取所有器件的图元 ID | ✓ |
| `getAll` | `getAll(layer?: TPCB_LayersOfComponent, primitiveLock?: boolean): Promise<Array<IPCB_PrimitiveComponent>>` | 获取所有器件 | ✓ |
| `getAllPinsByPrimitiveId` | `getAllPinsByPrimitiveId(primitiveId: string): Promise<Array<IPCB_PrimitiveComponentPad> \| undefined>` | 获取器件关联的所有焊盘 | ✓ |
| `placeComponentWithMouse` | `placeComponentWithMouse(component: { libraryUuid: string; uuid: string; } \| ILIB_DeviceItem \| ILIB_DeviceSearchItem): Promise<boolean>` | 使用鼠标放置器件 | ✓ |
| `placeFootprintWithMouse` | `placeFootprintWithMouse(footprint: { libraryUuid: string; uuid: string; } \| ILIB_FootprintItem \| ILIB_FootprintSearchItem, properties?: { [key: string]: boolean \| number \| string \| undefined; }): Promise<boolean>` | 使用鼠标放置封装 | ✓ |
| `getAllPropertyNames` | `getAllPropertyNames(): Promise<Array<string>>` | 获取所有器件的所有属性名称集合 | ✓ |

### `pcb_PrimitiveDimension` · PCB_PrimitiveDimension （live 可达 7/7）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `create` | `create(dimensionType: EPCB_PrimitiveDimensionType, coordinateSet: TPCB_PrimitiveDimensionCoordinateSet, layer?: TPCB_LayersOfDimension, unit?: ESYS_Unit.MILLIMETER \| ESYS_Unit.CENTIMETER \| ESYS_Unit.INCH \| ESYS_Unit.MIL, lineWidth?: number, precision?: number, primitiveLock?: boolean): Promise<IPCB_PrimitiveDimension \| undefined>` | 创建尺寸标注 | ✓ |
| `delete` | `delete(primitiveIds: string \| IPCB_PrimitiveDimension \| Array<string> \| Array<IPCB_PrimitiveDimension>): Promise<boolean>` | 删除尺寸标注 | ✓ |
| `modify` | `modify(primitiveId: string \| IPCB_PrimitiveDimension, property: { dimensionType?: EPCB_PrimitiveDimensionType; coordinateSet?: TPCB_PrimitiveDimensionCoordinateSet; layer?: TPCB_LayersOfDimension; unit?: ESYS_Unit.MILLIMETER \| ESYS_Unit.CENTIMETER \| ESYS_Unit.INCH \| ESYS_Unit.MIL; lineWidth?: number; precision?: number; primitiveLock?: boolean; }): Promise<IPCB_PrimitiveDimension \| undefined>` | 修改尺寸标注 | ✓ |
| `get` | `get(primitiveIds: string): Promise<IPCB_PrimitiveDimension \| undefined>` | 获取尺寸标注 | ✓ |
| `get` | `get(primitiveIds: Array<string>): Promise<Array<IPCB_PrimitiveDimension>>` | 获取尺寸标注 | ✓ |
| `getAllPrimitiveId` | `getAllPrimitiveId(layer?: TPCB_LayersOfDimension, primitiveLock?: boolean): Promise<Array<string>>` | 获取所有尺寸标注的图元 ID | ✓ |
| `getAll` | `getAll(layer?: TPCB_LayersOfDimension, primitiveLock?: boolean): Promise<Array<IPCB_PrimitiveDimension>>` | 获取所有尺寸标注 | ✓ |

### `pcb_PrimitiveFill` · PCB_PrimitiveFill （live 可达 7/7）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `create` | `create(layer: TPCB_LayersOfFill, complexPolygon: IPCB_Polygon, net?: string, fillMode?: EPCB_PrimitiveFillMode, lineWidth?: number, primitiveLock?: boolean): Promise<IPCB_PrimitiveFill \| undefined>` | 创建填充 | ✓ |
| `delete` | `delete(primitiveIds: string \| IPCB_PrimitiveFill \| Array<string> \| Array<IPCB_PrimitiveFill>): Promise<boolean>` | 删除填充 | ✓ |
| `modify` | `modify(primitiveId: string \| IPCB_PrimitiveFill, property: { layer?: TPCB_LayersOfFill; complexPolygon?: IPCB_Polygon; net?: string; fillMode?: EPCB_PrimitiveFillMode; lineWidth?: number; primitiveLock?: boolean; }): Promise<IPCB_PrimitiveFill \| undefined>` | 修改填充 | ✓ |
| `get` | `get(primitiveIds: string): Promise<IPCB_PrimitiveFill \| undefined>` | 获取填充 | ✓ |
| `get` | `get(primitiveIds: Array<string>): Promise<Array<IPCB_PrimitiveFill>>` | 获取填充 | ✓ |
| `getAllPrimitiveId` | `getAllPrimitiveId(layer?: TPCB_LayersOfFill, net?: string, primitiveLock?: boolean): Promise<Array<string>>` | 获取所有填充的图元 ID | ✓ |
| `getAll` | `getAll(layer?: TPCB_LayersOfFill, net?: string, primitiveLock?: boolean): Promise<Array<IPCB_PrimitiveFill>>` | 获取所有填充 | ✓ |

### `pcb_PrimitiveImage` · PCB_PrimitiveImage （live 可达 7/7）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `create` | `create(x: number, y: number, complexPolygon: TPCB_PolygonSourceArray \| Array<TPCB_PolygonSourceArray> \| IPCB_Polygon \| IPCB_ComplexPolygon, layer: TPCB_LayersOfImage, width?: number, height?: number, rotation?: number, horizonMirror?: boolean, primitiveLock?: boolean): Promise<IPCB_PrimitiveImage \| undefined>` | 创建图像 | ✓ |
| `delete` | `delete(primitiveIds: string \| IPCB_PrimitiveImage \| Array<string> \| Array<IPCB_PrimitiveImage>): Promise<boolean>` | 删除图像 | ✓ |
| `modify` | `modify(primitiveId: string \| IPCB_PrimitiveImage, property: { x?: number; y?: number; layer?: TPCB_LayersOfImage; width?: number; height?: number; rotation?: number; horizonMirror?: boolean; primitiveLock?: boolean; }): Promise<IPCB_PrimitiveImage \| undefined>` | 修改图像 | ✓ |
| `get` | `get(primitiveIds: string): Promise<IPCB_PrimitiveImage \| undefined>` | 获取图像 | ✓ |
| `get` | `get(primitiveIds: Array<string>): Promise<Array<IPCB_PrimitiveImage>>` | 获取图像 | ✓ |
| `getAllPrimitiveId` | `getAllPrimitiveId(layer?: TPCB_LayersOfImage, primitiveLock?: boolean): Promise<Array<string>>` | 获取所有图像的图元 ID | ✓ |
| `getAll` | `getAll(layer?: TPCB_LayersOfImage, primitiveLock?: boolean): Promise<Array<IPCB_PrimitiveImage>>` | 获取所有图像 | ✓ |

### `pcb_PrimitiveLine` · PCB_PrimitiveLine （live 可达 7/7）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `create` | `create(net: string, layer: TPCB_LayersOfLine, startX: number, startY: number, endX: number, endY: number, lineWidth?: number, primitiveLock?: boolean): Promise<IPCB_PrimitiveLine \| undefined>` | 创建直线 | ✓ |
| `delete` | `delete(primitiveIds: string \| IPCB_PrimitiveLine \| Array<string> \| Array<IPCB_PrimitiveLine>): Promise<boolean>` | 删除直线 | ✓ |
| `modify` | `modify(primitiveId: string \| IPCB_PrimitiveLine, property: { net?: string; layer?: TPCB_LayersOfLine; startX?: number; startY?: number; endX?: number; endY?: number; lineWidth?: number; primitiveLock?: boolean; }): Promise<IPCB_PrimitiveLine \| undefined>` | 修改直线 | ✓ |
| `get` | `get(primitiveIds: string): Promise<IPCB_PrimitiveLine \| undefined>` | 获取直线 | ✓ |
| `get` | `get(primitiveIds: Array<string>): Promise<Array<IPCB_PrimitiveLine>>` | 获取直线 | ✓ |
| `getAllPrimitiveId` | `getAllPrimitiveId(net?: string, layer?: TPCB_LayersOfLine, primitiveLock?: boolean): Promise<Array<string>>` | 获取所有直线的图元 ID | ✓ |
| `getAll` | `getAll(net?: string, layer?: TPCB_LayersOfLine, primitiveLock?: boolean): Promise<Array<IPCB_PrimitiveLine>>` | 获取所有直线 | ✓ |

### `pcb_PrimitiveObject` · PCB_PrimitiveObject （live 可达 7/7）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `create` | `create(layer: TPCB_LayersOfObject, topLeftX: number, topLeftY: number, binaryData: string, width: number, height: number, rotation?: number, mirror?: boolean, fileName?: string, primitiveLock?: boolean): Promise<IPCB_PrimitiveObject \| undefined>` | 创建二进制内嵌对象 | ✓ |
| `delete` | `delete(primitiveIds: string \| IPCB_PrimitiveObject \| Array<string> \| Array<IPCB_PrimitiveObject>): Promise<boolean>` | 删除二进制内嵌对象 | ✓ |
| `modify` | `modify(primitiveId: string \| IPCB_PrimitiveObject, property: { layer?: TPCB_LayersOfObject; topLeftX?: number; topLeftY?: number; binaryData?: string; width?: number; height?: number; rotation?: number; mirror?: boolean; fileName?: string; primitiveLock?: boolean; }): Promise<IPCB_PrimitiveObject \| undefined>` | 修改二进制内嵌对象 | ✓ |
| `get` | `get(primitiveIds: string): Promise<IPCB_PrimitiveObject \| undefined>` | 获取二进制内嵌对象 | ✓ |
| `get` | `get(primitiveIds: Array<string>): Promise<Array<IPCB_PrimitiveObject>>` | 获取二进制内嵌对象 | ✓ |
| `getAllPrimitiveId` | `getAllPrimitiveId(layer?: TPCB_LayersOfObject, primitiveLock?: boolean): Promise<Array<string>>` | 获取所有二进制内嵌对象的图元 ID | ✓ |
| `getAll` | `getAll(layer?: TPCB_LayersOfObject, primitiveLock?: boolean): Promise<Array<IPCB_PrimitiveObject>>` | 获取所有二进制内嵌对象 | ✓ |

### `pcb_PrimitivePad` · PCB_PrimitivePad （live 可达 7/7）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `create` | `create(layer: TPCB_LayersOfPad, padNumber: string, x: number, y: number, rotation?: number, pad?: TPCB_PrimitivePadShape, net?: string, hole?: TPCB_PrimitivePadHole \| null, holeOffsetX?: number, holeOffsetY?: number, holeRotation?: number, metallization?: boolean, padType?: EPCB_PrimitivePadType, specialPad?: TPCB_PrimitiveSpecialPadShape, solderMaskAndPasteMaskExpansion?: IPCB_PrimitiveSolderMaskAndPasteMaskExpansion \| null, heatWelding?: IPCB_PrimitivePadHeatWelding \| null, primitiveLock?: boolean): Promise<IPCB_PrimitivePad \| undefined>` | 创建焊盘 | ✓ |
| `delete` | `delete(primitiveIds: string \| IPCB_PrimitivePad \| Array<string> \| Array<IPCB_PrimitivePad>): Promise<boolean>` | 删除焊盘 | ✓ |
| `modify` | `modify(primitiveId: string \| IPCB_PrimitivePad, property: { layer?: TPCB_LayersOfPad; padNumber?: string; x?: number; y?: number; rotation?: number; pad?: TPCB_PrimitivePadShape; net?: string; hole?: TPCB_PrimitivePadHole \| null; holeOffsetX?: number; holeOffsetY?: number; holeRotation?: number; metallization?: boolean; specialPad?: TPCB_PrimitiveSpecialPadShape; solderMaskAndPasteMaskExpansion?: IPCB_PrimitiveSolderMaskAndPasteMaskExpansion \| null; heatWelding?: IPCB_PrimitivePadHeatWelding \| null; primitiveLock?: boolean; }): Promise<IPCB_PrimitivePad \| undefined>` | 修改焊盘 | ✓ |
| `get` | `get(primitiveIds: string): Promise<IPCB_PrimitivePad \| undefined>` | 获取焊盘 | ✓ |
| `get` | `get(primitiveIds: Array<string>): Promise<Array<IPCB_PrimitivePad>>` | 获取焊盘 | ✓ |
| `getAllPrimitiveId` | `getAllPrimitiveId(layer?: TPCB_LayersOfPad, net?: string, primitiveLock?: boolean, padType?: EPCB_PrimitivePadType): Promise<Array<string>>` | 获取所有焊盘的图元 ID | ✓ |
| `getAll` | `getAll(layer?: TPCB_LayersOfPad, net?: string, primitiveLock?: boolean, padType?: EPCB_PrimitivePadType): Promise<Array<IPCB_PrimitivePad>>` | 获取所有焊盘 | ✓ |

### `pcb_PrimitivePolyline` · PCB_PrimitivePolyline （live 可达 7/7）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `create` | `create(net: string, layer: TPCB_LayersOfLine, polygon: IPCB_Polygon, lineWidth?: number, primitiveLock?: boolean): Promise<IPCB_PrimitivePolyline \| undefined>` | 创建折线 | ✓ |
| `delete` | `delete(primitiveIds: string \| IPCB_PrimitivePolyline \| Array<string> \| Array<IPCB_PrimitivePolyline>): Promise<boolean>` | 删除折线 | ✓ |
| `modify` | `modify(primitiveId: string \| IPCB_PrimitivePolyline, property: { net?: string; layer?: TPCB_LayersOfLine; polygon?: IPCB_Polygon; lineWidth?: number; primitiveLock?: boolean; }): Promise<IPCB_PrimitivePolyline \| undefined>` | 修改折线 | ✓ |
| `get` | `get(primitiveIds: string): Promise<IPCB_PrimitivePolyline \| undefined>` | 获取折线 | ✓ |
| `get` | `get(primitiveIds: Array<string>): Promise<Array<IPCB_PrimitivePolyline>>` | 获取折线 | ✓ |
| `getAllPrimitiveId` | `getAllPrimitiveId(net?: string, layer?: TPCB_LayersOfLine, primitiveLock?: boolean): Promise<Array<string>>` | 获取所有折线的图元 ID | ✓ |
| `getAll` | `getAll(net?: string, layer?: TPCB_LayersOfLine, primitiveLock?: boolean): Promise<Array<IPCB_PrimitivePolyline>>` | 获取所有折线 | ✓ |

### `pcb_PrimitivePour` · PCB_PrimitivePour （live 可达 7/7）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `create` | `create(net: string, layer: TPCB_LayersOfCopper, complexPolygon: IPCB_Polygon, pourFillMethod?: EPCB_PrimitivePourFillMethod, preserveSilos?: boolean, pourName?: string, pourPriority?: number, lineWidth?: number, primitiveLock?: boolean): Promise<IPCB_PrimitivePour \| undefined>` | 创建覆铜边框 | ✓ |
| `delete` | `delete(primitiveIds: string \| IPCB_PrimitivePour \| Array<string> \| Array<IPCB_PrimitivePour>): Promise<boolean>` | 删除覆铜边框 | ✓ |
| `modify` | `modify(primitiveId: string \| IPCB_PrimitivePour, property: { net?: string; layer?: TPCB_LayersOfCopper; complexPolygon?: IPCB_Polygon; pourFillMethod?: EPCB_PrimitivePourFillMethod; preserveSilos?: boolean; pourName?: string; pourPriority?: number; lineWidth?: number; primitiveLock?: boolean; }): Promise<IPCB_PrimitivePour \| undefined>` | 修改覆铜边框 | ✓ |
| `get` | `get(primitiveIds: string): Promise<IPCB_PrimitivePour \| undefined>` | 获取覆铜边框 | ✓ |
| `get` | `get(primitiveIds: Array<string>): Promise<Array<IPCB_PrimitivePour>>` | 获取覆铜边框 | ✓ |
| `getAllPrimitiveId` | `getAllPrimitiveId(net?: string, layer?: TPCB_LayersOfCopper, primitiveLock?: boolean): Promise<Array<string>>` | 获取所有覆铜边框的图元 ID | ✓ |
| `getAll` | `getAll(net?: string, layer?: TPCB_LayersOfCopper, primitiveLock?: boolean): Promise<Array<IPCB_PrimitivePour>>` | 获取所有覆铜边框图元 | ✓ |

### `pcb_PrimitivePoured` · PCB_PrimitivePoured （live 可达 7/7）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `create` | `create(): undefined` | 创建覆铜填充 | ✓ |
| `delete` | `delete(primitiveIds: string \| IPCB_PrimitivePoured \| Array<string> \| Array<IPCB_PrimitivePoured>): Promise<boolean>` | 删除覆铜填充 | ✓ |
| `modify` | `modify(): undefined` | 修改覆铜填充 | ✓ |
| `get` | `get(primitiveIds: string): Promise<IPCB_PrimitivePoured \| undefined>` | 获取覆铜填充 | ✓ |
| `get` | `get(primitiveIds: Array<string>): Promise<Array<IPCB_PrimitivePoured>>` | 获取覆铜填充 | ✓ |
| `getAllPrimitiveId` | `getAllPrimitiveId(): Promise<Array<string>>` | 获取所有覆铜填充的图元 ID | ✓ |
| `getAll` | `getAll(): Promise<Array<IPCB_PrimitivePoured>>` | 获取所有覆铜填充图元 | ✓ |

### `pcb_PrimitiveRegion` · PCB_PrimitiveRegion （live 可达 7/7）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `create` | `create(layer: TPCB_LayersOfRegion, complexPolygon: IPCB_Polygon, ruleType?: Array<EPCB_PrimitiveRegionRuleType>, regionName?: string, lineWidth?: number, primitiveLock?: boolean): Promise<IPCB_PrimitiveRegion \| undefined>` | 创建区域 | ✓ |
| `delete` | `delete(primitiveIds: string \| IPCB_PrimitiveRegion \| Array<string> \| Array<IPCB_PrimitiveRegion>): Promise<boolean>` | 删除区域 | ✓ |
| `modify` | `modify(primitiveId: string \| IPCB_PrimitiveRegion, property: { layer?: TPCB_LayersOfRegion; complexPolygon?: IPCB_Polygon; ruleType?: Array<EPCB_PrimitiveRegionRuleType>; regionName?: string; lineWidth?: number; primitiveLock?: boolean; }): Promise<IPCB_PrimitiveRegion \| undefined>` | 修改区域 | ✓ |
| `get` | `get(primitiveIds: string): Promise<IPCB_PrimitiveRegion \| undefined>` | 获取区域 | ✓ |
| `get` | `get(primitiveIds: Array<string>): Promise<Array<IPCB_PrimitiveRegion>>` | 获取区域 | ✓ |
| `getAllPrimitiveId` | `getAllPrimitiveId(layer?: TPCB_LayersOfRegion, ruleType?: Array<EPCB_PrimitiveRegionRuleType>, primitiveLock?: boolean): Promise<Array<string>>` | 获取所有区域的图元 ID | ✓ |
| `getAll` | `getAll(layer?: TPCB_LayersOfRegion, ruleType?: Array<EPCB_PrimitiveRegionRuleType>, primitiveLock?: boolean): Promise<Array<IPCB_PrimitiveRegion>>` | 获取所有区域 | ✓ |

### `pcb_PrimitiveString` · PCB_PrimitiveString （live 可达 7/7）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `create` | `create(layer: TPCB_LayersOfImage, x: number, y: number, text: string, fontFamily: string, fontSize: number, lineWidth: number, alignMode: EPCB_PrimitiveStringAlignMode, rotation: number, reverse: boolean, expansion: number, mirror: boolean, primitiveLock: boolean): Promise<IPCB_PrimitiveString \| undefined>` | 创建文本 | ✓ |
| `delete` | `delete(primitiveIds: string \| IPCB_PrimitiveString \| Array<string> \| Array<IPCB_PrimitiveString>): Promise<boolean>` | 删除文本 | ✓ |
| `modify` | `modify(primitiveId: string \| IPCB_PrimitiveString, property: { layer?: TPCB_LayersOfImage; x?: number; y?: number; text?: string; fontFamily?: string; fontSize?: number; lineWidth?: number; alignMode?: EPCB_PrimitiveStringAlignMode; rotation?: number; reverse?: boolean; expansion?: number; mirror?: boolean; primitiveLock?: boolean; }): Promise<IPCB_PrimitiveString \| undefined>` | 修改文本 | ✓ |
| `get` | `get(primitiveIds: string): Promise<IPCB_PrimitiveString \| undefined>` | 获取文本 | ✓ |
| `get` | `get(primitiveIds: Array<string>): Promise<Array<IPCB_PrimitiveString>>` | 获取文本 | ✓ |
| `getAllPrimitiveId` | `getAllPrimitiveId(layer?: TPCB_LayersOfImage, primitiveLock?: boolean): Promise<Array<string>>` | 获取所有文本的图元 ID | ✓ |
| `getAll` | `getAll(layer?: TPCB_LayersOfImage, primitiveLock?: boolean): Promise<Array<IPCB_PrimitiveString>>` | 获取所有文本 | ✓ |

### `pcb_PrimitiveVia` · PCB_PrimitiveVia （live 可达 7/7）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `create` | `create(net: string, x: number, y: number, holeDiameter: number, diameter: number, viaType?: EPCB_PrimitiveViaType, designRuleBlindViaName?: string \| null, solderMaskExpansion?: IPCB_PrimitiveSolderMaskAndPasteMaskExpansion \| null, primitiveLock?: boolean): Promise<IPCB_PrimitiveVia \| undefined>` | 创建过孔 | ✓ |
| `delete` | `delete(primitiveIds: string \| IPCB_PrimitiveVia \| Array<string> \| Array<IPCB_PrimitiveVia>): Promise<boolean>` | 删除过孔 | ✓ |
| `modify` | `modify(primitiveId: string \| IPCB_PrimitiveVia, property: { net?: string; x?: number; y?: number; holeDiameter?: number; diameter?: number; viaType?: EPCB_PrimitiveViaType; designRuleBlindViaName?: string \| null; solderMaskExpansion?: IPCB_PrimitiveSolderMaskAndPasteMaskExpansion \| null; primitiveLock?: boolean; }): Promise<IPCB_PrimitiveVia \| undefined>` | 修改过孔 | ✓ |
| `get` | `get(primitiveIds: string): Promise<IPCB_PrimitiveVia \| undefined>` | 获取过孔 | ✓ |
| `get` | `get(primitiveIds: Array<string>): Promise<Array<IPCB_PrimitiveVia>>` | 获取过孔 | ✓ |
| `getAllPrimitiveId` | `getAllPrimitiveId(net?: string, primitiveLock?: boolean): Promise<Array<string>>` | 获取所有过孔图元 ID | ✓ |
| `getAll` | `getAll(net?: string, primitiveLock?: boolean): Promise<Array<IPCB_PrimitiveVia>>` | 获取所有过孔 | ✓ |

### `pcb_RayTracerEngine` · PCB_RayTracerEngine （live 可达 3/3）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `init` | `init(lut: Array<{ [key: string]: any; }>): Promise<void>` | 初始化光线追踪引擎 | ✓ |
| `dispose` | `dispose(): Promise<void>` | 停止光线追踪引擎 | ✓ |
| `setRenderConfigurations` | `setRenderConfigurations(configurations: any): Promise<void>` | 设置光线追踪渲染配置 | ✓ |

### `pcb_SelectControl` · PCB_SelectControl （live 可达 8/8）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `getAllSelectedPrimitives_PrimitiveId` | `getAllSelectedPrimitives_PrimitiveId(): Promise<Array<string>>` | 查询所有已选中图元的图元 ID | ✓ |
| `getAllSelectedPrimitives` | `getAllSelectedPrimitives(): Promise<Array<IPCB_Primitive>>` | 查询所有已选中图元的图元对象 | ✓ |
| `getSelectedPrimitives` | `getSelectedPrimitives(): Promise<Array<Object>>` | 查询选中图元的所有参数 | ✓ |
| `doSelectPrimitives` | `doSelectPrimitives(primitiveIds: string \| Array<string>): Promise<boolean>` | 使用图元 ID 选中图元 | ✓ |
| `doCrossProbeSelect` | `doCrossProbeSelect(components?: Array<string>, pins?: Array<string>, nets?: Array<string>, highlight?: boolean, select?: boolean): Promise<boolean>` | 进行交叉选择 | ✓ |
| `doCrossProbeSelectByObject` | `doCrossProbeSelectByObject(components?: Array<string>, pins?: Array<string>, nets?: Array<string>): Promise<boolean>` | 进行交叉选择 | ✓ |
| `clearSelected` | `clearSelected(): Promise<boolean>` | 清除选中 | ✓ |
| `getCurrentMousePosition` | `getCurrentMousePosition(): Promise<{ x: number; y: number; } \| undefined>` | 获取当前鼠标在画布上的位置 | ✓ |

## SCH · 原理图（图元/网络/网表/DRC/仿真/制造）

### `sch_Document` · SCH_Document （live 可达 9/9）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `importChanges` | `importChanges(): Promise<boolean>` | 从 PCB 导入变更 | ✓ |
| `save` | `save(): Promise<boolean>` | 保存文档 | ✓ |
| `navigateToCoordinates` | `navigateToCoordinates(x: number, y: number): Promise<boolean>` | 定位到画布坐标 | ✓ |
| `navigateToRegion` | `navigateToRegion(left: number, right: number, top: number, bottom: number): Promise<boolean>` | 定位到画布区域 | ✓ |
| `getPrimitiveAtPoint` | `getPrimitiveAtPoint(x: number, y: number): ISCH_Primitive \| undefined` | 获取坐标点的图元 | ✓ |
| `getPrimitivesInRegion` | `getPrimitivesInRegion(left: number, right: number, top: number, bottom: number): Array<ISCH_Primitive>` | 获取区域内所有图元 | ✓ |
| `getCurrentFilterConfiguration` | `getCurrentFilterConfiguration(): Promise<{ [key: string]: any; } \| undefined>` | 获取当前画布过滤器配置 | ✓ |
| `autoRouting` | `autoRouting(props?: { uuids?: Array<string>; netlist?: { component: { [uniqueId: string]: { pinInfoMap: { [key: string]: { name: string; number: string; net: string; props: { 'Pin Number': string; }; }; }; }; }; }; designatorDeviceTypeMap?: { [designator: string]: 'resistor' \| 'capacitor' \| 'inductive' \| 'diode' \| 'triode' \| 'oscillator' \| 'chip' \| 'otherDevice'; }; }): Promise<any>` | 自动布线 | ✓ |
| `autoLayout` | `autoLayout(props?: { uuids?: Array<string>; netlist?: { component: { [uniqueId: string]: { pinInfoMap: { [key: string]: { name: string; number: string; net: string; props: { 'Pin Number': string; }; }; }; }; }; }; designatorDeviceTypeMap?: { [designator: string]: 'resistor' \| 'capacitor' \| 'inductive' \| 'diode' \| 'triode' \| 'oscillator' \| 'chip' \| 'otherDevice'; }; }): Promise<any>` | 自动布局 | ✓ |

### `sch_Drc` · SCH_Drc （live 可达 2/2）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `check` | `check(strict: boolean, userInterface: boolean, includeVerboseError: false): Promise<boolean>` | 检查 DRC | ✓ |
| `check` | `check(strict: boolean, userInterface: boolean, includeVerboseError: true): Promise<Array<any>>` | 检查 DRC | ✓ |

### `sch_Event` · SCH_Event （live 可达 5/5）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `addMouseEventListener` | `addMouseEventListener(id: string, eventType: 'all' \| ESCH_MouseEventType, callFn: (eventType: ESCH_MouseEventType) => void \| Promise<void>, onlyOnce?: boolean): void` | 新增鼠标事件监听 | ✓ |
| `addPrimitiveEventListener` | `addPrimitiveEventListener(id: string, eventType: 'all' \| ESCH_PrimitiveEventType, callFn: (eventType: ESCH_PrimitiveEventType, props: { primitiveIds: Array<string>; }) => void \| Promise<void>, onlyOnce?: boolean): void` | 新增图元事件监听 | ✓ |
| `addSimulationEnginePullEventListener` | `addSimulationEnginePullEventListener(id: string, eventType: 'all', callFn: (eventType: ESCH_DynamicSimulationEnginePullEventType \| ESCH_SpiceSimulationEnginePullEventType, props: { [key: string]: any; }) => void \| Promise<void>): void` | 注册仿真引擎拉取事件监听 | ✓ |
| `removeEventListener` | `removeEventListener(id: string): boolean` | 移除事件监听 | ✓ |
| `isEventListenerAlreadyExist` | `isEventListenerAlreadyExist(id: string): boolean` | 查询事件监听是否存在 | ✓ |

### `sch_ManufactureData` · SCH_ManufactureData （live 可达 11/11）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `getAssemblyVariantsConfigs` | `getAssemblyVariantsConfigs(): Promise<Array<{ text: string; value: string; }>>` | 获取装配体变量配置列表 | ✓ |
| `getBomTemplates` | `getBomTemplates(): Promise<Array<string>>` | 获取 BOM 模板列表 | ✓ |
| `uploadBomTemplateFile` | `uploadBomTemplateFile(templateFile: File, template?: string): Promise<string \| undefined>` | 上传 BOM 模板文件 | ✓ |
| `getBomTemplateFile` | `getBomTemplateFile(template: string): Promise<File \| undefined>` | 获取 BOM 模板文件 | ✓ |
| `deleteBomTemplate` | `deleteBomTemplate(template: string): Promise<boolean>` | 删除 BOM 模板 | ✓ |
| `getBomFile` | `getBomFile(fileName?: string, fileType?: 'xlsx' \| 'csv', template?: string, filterOptions?: Array<{ property: string; includeValue: boolean \| string; }>, statistics?: Array<string>, property?: Array<string>, columns?: Array<IPCB_BomPropertiesTableColumns>, assemblyVariantsConfig?: { text: string; value: string; }): Promise<File \| undefined>` | 获取 BOM 文件 | ✓ |
| `getNetlistFile` | `getNetlistFile(fileName?: string, netlistType?: ESYS_NetlistType): Promise<File \| undefined>` | 获取网表文件（Netlist） | ✓ |
| `getSimulationNetlistFile` | `getSimulationNetlistFile(fileName?: string, netlistType?: ESCH_SimulationNetlistType): Promise<File \| undefined>` | 获取仿真网表文件 | ✓ |
| `getExportDocumentFile` | `getExportDocumentFile(fileName?: string, fileType?: ESCH_ExportDocumentFileType, typeSpecificParams?: { theme?: 'Default' \| 'White on Black' \| 'Black on White'; lineWidth?: 'Default' \| 'Always 1px' \| 'Follow the Zoom Change'; displayAttributesAsMenu?: boolean; size?: 'Original Size' \| string \| { width: number; height: number; unit: ESYS_Unit.INCH \| ESYS_Unit.MILLIMETER; }; }, object?: 'All Schematic' \| 'Current Schematic' \| 'Current Schematic Page' \| string, objectSpecificParams?: { range?: 'All' \| [number, number]; outputMethod?: 'Merged sheet' \| 'Separated sheet'; }): Promise<File \| undefined>` | 获取导出文档文件 | ✓ |
| `placeComponentsOrder` | `placeComponentsOrder(interactive?: boolean, ignoreWarning?: boolean): Promise<boolean>` | 元件下单 | ✓ |
| `placeSmtComponentsOrder` | `placeSmtComponentsOrder(interactive?: boolean, ignoreWarning?: boolean): Promise<boolean>` | SMT 元件下单 | ✓ |

### `sch_Net` · SCH_Net （live 可达 4/4）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `getCurrentProjectAllNets` | `getCurrentProjectAllNets(): Promise<Array<ISCH_ProjectNetInfo>>` | 获取当前工程下所有网络的详细信息 | ✓ |
| `getAllNets` | `getAllNets(): Promise<Array<ISCH_NetInfo>>` | 获取所有网络的详细信息 | ✓ |
| `getNet` | `getNet(net: string): Promise<ISCH_NetInfo \| undefined>` | 获取指定网络的详细信息 | ✓ |
| `getAllNetsName` | `getAllNetsName(): Promise<Array<string>>` | 获取所有网络的网络名称 | ✓ |

### `sch_Netlist` · SCH_Netlist （live 可达 2/2）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `getNetlist` | `getNetlist(type?: ESYS_NetlistType): Promise<string>` | 获取网表 | ✓ |
| `setNetlist` | `setNetlist(type: ESYS_NetlistType \| undefined, netlist: string): Promise<void>` | 更新网表 | ✓ |

### `sch_Primitive` · SCH_Primitive （live 可达 4/4）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `getPrimitiveTypeByPrimitiveId` | `getPrimitiveTypeByPrimitiveId(id: string): Promise<ESCH_PrimitiveType \| undefined>` | 获取指定 ID 的图元的图元类型 | ✓ |
| `getPrimitiveByPrimitiveId` | `getPrimitiveByPrimitiveId(id: string): Promise<ISCH_Primitive \| undefined>` | 获取指定 ID 的图元的所有属性 | ✓ |
| `getPrimitivesByPrimitiveId` | `getPrimitivesByPrimitiveId(ids: Array<string>): Promise<Array<ISCH_Primitive>>` | 获取指定所有 ID 的图元的所有属性 | ✓ |
| `getPrimitivesBBox` | `getPrimitivesBBox(primitiveIds: Array<string \| ISCH_Primitive>): Promise<{ minX: number; minY: number; maxX: number; maxY: number; } \| undefined>` | 获取图元的 BBox | ✓ |

### `sch_PrimitiveArc` · SCH_PrimitiveArc （live 可达 7/7）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `create` | `create(startX: number, startY: number, referenceX: number, referenceY: number, endX: number, endY: number, color?: string \| null, fillColor?: string \| null, lineWidth?: number \| null, lineType?: ESCH_PrimitiveLineType \| null): Promise<ISCH_PrimitiveArc \| undefined>` | 创建圆弧 | ✓ |
| `delete` | `delete(primitiveIds: string \| ISCH_PrimitiveArc \| Array<string> \| Array<ISCH_PrimitiveArc>): Promise<boolean>` | 删除圆弧 | ✓ |
| `modify` | `modify(primitiveId: string \| ISCH_PrimitiveArc, property: { startX?: number; startY?: number; referenceX?: number; referenceY?: number; endX?: number; endY?: number; color?: string \| null; fillColor?: string \| null; lineWidth?: number \| null; lineType?: ESCH_PrimitiveLineType \| null; }): Promise<ISCH_PrimitiveArc \| undefined>` | 修改圆弧 | ✓ |
| `get` | `get(primitiveIds: string): Promise<ISCH_PrimitiveArc \| undefined>` | 获取圆弧 | ✓ |
| `get` | `get(primitiveIds: Array<string>): Promise<Array<ISCH_PrimitiveArc>>` | 获取圆弧 | ✓ |
| `getAllPrimitiveId` | `getAllPrimitiveId(): Promise<Array<string>>` | 获取所有圆弧的图元 ID | ✓ |
| `getAll` | `getAll(): Promise<Array<ISCH_PrimitiveArc>>` | 获取所有圆弧 | ✓ |

### `sch_PrimitiveAttribute` · SCH_PrimitiveAttribute （live 可达 8/8）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `create` | `create(): undefined` | 创建属性 | ✓ |
| `delete` | `delete(): boolean` | 删除属性 | ✓ |
| `modify` | `modify(primitiveId: string \| ISCH_PrimitiveAttribute, property: { x?: number \| null; y?: number \| null; rotation?: number \| null; color?: string \| null; fontName?: string \| null; fontSize?: number \| null; bold?: boolean \| null; italic?: boolean \| null; underLine?: boolean \| null; alignMode?: ESCH_PrimitiveTextAlignMode \| null; fillColor?: string \| null; key?: string; value?: string; keyVisible?: boolean \| null; valueVisible?: boolean \| null; }): Promise<ISCH_PrimitiveAttribute \| undefined>` | 修改属性 | ✓ |
| `get` | `get(primitiveIds: string): Promise<ISCH_PrimitiveAttribute \| undefined>` | 获取属性 | ✓ |
| `get` | `get(primitiveIds: Array<string>): Promise<Array<ISCH_PrimitiveAttribute>>` | 获取属性 | ✓ |
| `getAllPrimitiveId` | `getAllPrimitiveId(parentPrimitiveId?: string): Promise<Array<string>>` | 获取所有属性的图元 ID | ✓ |
| `getAll` | `getAll(parentPrimitiveId?: string): Promise<Array<ISCH_PrimitiveAttribute>>` | 获取所有属性 | ✓ |
| `createNetLabel` | `createNetLabel(x: number, y: number, net: string): Promise<ISCH_PrimitiveAttribute \| undefined>` | 创建网络标签 | ✓ |

### `sch_PrimitiveBus` · SCH_PrimitiveBus （live 可达 7/7）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `create` | `create(busName: string, line: Array<number> \| Array<Array<number>>, color?: string \| null, lineWidth?: number \| null, lineType?: ESCH_PrimitiveLineType \| null): Promise<ISCH_PrimitiveBus \| undefined>` | 创建总线 | ✓ |
| `delete` | `delete(primitiveIds: string \| ISCH_PrimitiveBus \| Array<string> \| Array<ISCH_PrimitiveBus>): Promise<boolean>` | 删除总线 | ✓ |
| `modify` | `modify(primitiveId: string \| ISCH_PrimitiveBus, property: { busName?: string; line?: Array<number> \| Array<Array<number>>; color?: string \| null; lineWidth?: number \| null; lineType?: ESCH_PrimitiveLineType \| null; }): Promise<ISCH_PrimitiveBus \| undefined>` | 修改总线 | ✓ |
| `get` | `get(primitiveIds: string): Promise<ISCH_PrimitiveBus \| undefined>` | 获取总线 | ✓ |
| `get` | `get(primitiveIds: Array<string>): Promise<Array<ISCH_PrimitiveBus>>` | 获取总线 | ✓ |
| `getAllPrimitiveId` | `getAllPrimitiveId(): Promise<Array<string>>` | 获取所有总线的图元 ID | ✓ |
| `getAll` | `getAll(): Promise<Array<ISCH_PrimitiveBus>>` | 获取所有总线 | ✓ |

### `sch_PrimitiveCircle` · SCH_PrimitiveCircle （live 可达 7/7）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `create` | `create(centerX: number, centerY: number, radius: number, color?: string \| null, fillColor?: string \| null, lineWidth?: number \| null, lineType?: ESCH_PrimitiveLineType \| null, fillStyle?: ESCH_PrimitiveFillStyle \| null): Promise<ISCH_PrimitiveCircle>` | 创建圆 | ✓ |
| `delete` | `delete(primitiveIds: string \| ISCH_PrimitiveCircle \| Array<string> \| Array<ISCH_PrimitiveCircle>): Promise<boolean>` | 删除圆 | ✓ |
| `modify` | `modify(primitiveId: string \| ISCH_PrimitiveCircle, property: { centerX?: number; centerY?: number; radius?: number; color?: string \| null; fillColor?: string \| null; lineWidth?: number \| null; lineType?: ESCH_PrimitiveLineType \| null; fillStyle?: ESCH_PrimitiveFillStyle \| null; }): Promise<ISCH_PrimitiveCircle \| undefined>` | 修改圆 | ✓ |
| `get` | `get(primitiveIds: string): Promise<ISCH_PrimitiveCircle \| undefined>` | 获取圆 | ✓ |
| `get` | `get(primitiveIds: Array<string>): Promise<Array<ISCH_PrimitiveCircle>>` | 获取圆 | ✓ |
| `getAllPrimitiveId` | `getAllPrimitiveId(): Promise<Array<string>>` | 获取所有圆的图元 ID | ✓ |
| `getAll` | `getAll(): Promise<Array<ISCH_PrimitiveCircle>>` | 获取所有圆 | ✓ |

### `sch_PrimitiveComponent` · SCH_PrimitiveComponent （live 可达 20/20）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `setNetFlagComponentUuid_Power` | `setNetFlagComponentUuid_Power(component: { libraryUuid: string; uuid: string; } \| ILIB_DeviceItem \| ILIB_DeviceSearchItem): Promise<boolean>` | 设置在扩展 API 中 Power 网络标识关联的器件 UUID | ✓ |
| `setNetFlagComponentUuid_Ground` | `setNetFlagComponentUuid_Ground(component: { libraryUuid: string; uuid: string; } \| ILIB_DeviceItem \| ILIB_DeviceSearchItem): Promise<boolean>` | 设置在扩展 API 中 Ground 网络标识关联的器件 UUID | ✓ |
| `setNetFlagComponentUuid_AnalogGround` | `setNetFlagComponentUuid_AnalogGround(component: { libraryUuid: string; uuid: string; } \| ILIB_DeviceItem \| ILIB_DeviceSearchItem): Promise<boolean>` | 设置在扩展 API 中 AnalogGround 网络标识关联的器件 UUID | ✓ |
| `setNetFlagComponentUuid_ProtectGround` | `setNetFlagComponentUuid_ProtectGround(component: { libraryUuid: string; uuid: string; } \| ILIB_DeviceItem \| ILIB_DeviceSearchItem): Promise<boolean>` | 设置在扩展 API 中 ProtectGround 网络标识关联的器件 UUID | ✓ |
| `setNetPortComponentUuid_IN` | `setNetPortComponentUuid_IN(component: { libraryUuid: string; uuid: string; } \| ILIB_DeviceItem \| ILIB_DeviceSearchItem): Promise<boolean>` | 设置在扩展 API 中 IN 网络端口关联的器件 UUID | ✓ |
| `setNetPortComponentUuid_OUT` | `setNetPortComponentUuid_OUT(component: { libraryUuid: string; uuid: string; } \| ILIB_DeviceItem \| ILIB_DeviceSearchItem): Promise<boolean>` | 设置在扩展 API 中 OUT 网络端口关联的器件 UUID | ✓ |
| `setNetPortComponentUuid_BI` | `setNetPortComponentUuid_BI(component: { libraryUuid: string; uuid: string; } \| ILIB_DeviceItem \| ILIB_DeviceSearchItem): Promise<boolean>` | 设置在扩展 API 中 BI 网络端口关联的器件 UUID | ✓ |
| `create` | `create(component: { libraryUuid: string; uuid: string; } \| ILIB_DeviceItem \| ILIB_DeviceSearchItem, x: number, y: number, subPartName?: string, rotation?: number, mirror?: boolean, addIntoBom?: boolean, addIntoPcb?: boolean): Promise<ISCH_PrimitiveComponent$1 \| undefined>` | 创建器件 | ✓ |
| `createNetFlag` | `createNetFlag(identification: 'Power' \| 'Ground' \| 'AnalogGround' \| 'ProtectGround', net: string, x: number, y: number, rotation?: number, mirror?: boolean): Promise<ISCH_PrimitiveComponent$1 \| undefined>` | 创建网络标识 | ✓ |
| `createNetPort` | `createNetPort(direction: 'IN' \| 'OUT' \| 'BI', net: string, x: number, y: number, rotation?: number, mirror?: boolean): Promise<ISCH_PrimitiveComponent$1 \| undefined>` | 创建网络端口 | ✓ |
| `createShortCircuitFlag` | `createShortCircuitFlag(x: number, y: number, rotation?: number, mirror?: boolean): Promise<ISCH_PrimitiveComponent$1 \| undefined>` | 创建短接标识 | ✓ |
| `delete` | `delete(primitiveIds: string \| ISCH_PrimitiveComponent$1 \| Array<string> \| Array<ISCH_PrimitiveComponent$1>): Promise<boolean>` | 删除器件 | ✓ |
| `modify` | `modify(primitiveId: string \| ISCH_PrimitiveComponent$1, property: { x?: number; y?: number; rotation?: number; mirror?: boolean; addIntoBom?: boolean; addIntoPcb?: boolean; designator?: string \| null; name?: string \| null; uniqueId?: string \| null; manufacturer?: string \| null; manufacturerId?: string \| null; supplier?: string \| null; supplierId?: string \| null; otherProperty?: { [key: string]: string \| number \| boolean; }; }): Promise<ISCH_PrimitiveComponent$1 \| undefined>` | 修改器件 | ✓ |
| `get` | `get(primitiveIds: string): Promise<ISCH_PrimitiveComponent$1 \| undefined>` | 获取器件 | ✓ |
| `get` | `get(primitiveIds: Array<string>): Promise<Array<ISCH_PrimitiveComponent$1>>` | 获取器件 | ✓ |
| `getAllPrimitiveId` | `getAllPrimitiveId(componentType?: ESCH_PrimitiveComponentType$1, allSchematicPages?: boolean): Promise<Array<string>>` | 获取所有器件的图元 ID | ✓ |
| `getAll` | `getAll(componentType?: ESCH_PrimitiveComponentType$1, allSchematicPages?: boolean): Promise<Array<ISCH_PrimitiveComponent$1>>` | 获取所有器件 | ✓ |
| `getAllPinsByPrimitiveId` | `getAllPinsByPrimitiveId(primitiveId: string): Promise<Array<ISCH_PrimitiveComponentPin> \| undefined>` | 获取器件关联的所有引脚 | ✓ |
| `placeComponentWithMouse` | `placeComponentWithMouse(component: { libraryUuid: string; uuid: string; } \| ILIB_DeviceItem \| ILIB_DeviceSearchItem, subPartName?: string): Promise<boolean>` | 使用鼠标放置器件 | ✓ |
| `getAllPropertyNames` | `getAllPropertyNames(): Promise<Array<string>>` | 获取所有器件的所有属性名称集合 | ✓ |

### `sch_PrimitiveComponent3` · SCH_PrimitiveComponent3 （运行期未抽样）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `setNetFlagComponentUuid_Power` | `setNetFlagComponentUuid_Power(component: { libraryUuid: string; uuid: string; } \| ILIB_DeviceItem \| ILIB_DeviceSearchItem): Promise<boolean>` | 设置在扩展 API 中 Power 网络标识关联的器件 UUID | ? |
| `setNetFlagComponentUuid_Ground` | `setNetFlagComponentUuid_Ground(component: { libraryUuid: string; uuid: string; } \| ILIB_DeviceItem \| ILIB_DeviceSearchItem): Promise<boolean>` | 设置在扩展 API 中 Ground 网络标识关联的器件 UUID | ? |
| `setNetFlagComponentUuid_AnalogGround` | `setNetFlagComponentUuid_AnalogGround(component: { libraryUuid: string; uuid: string; } \| ILIB_DeviceItem \| ILIB_DeviceSearchItem): Promise<boolean>` | 设置在扩展 API 中 AnalogGround 网络标识关联的器件 UUID | ? |
| `setNetFlagComponentUuid_ProtectGround` | `setNetFlagComponentUuid_ProtectGround(component: { libraryUuid: string; uuid: string; } \| ILIB_DeviceItem \| ILIB_DeviceSearchItem): Promise<boolean>` | 设置在扩展 API 中 ProtectGround 网络标识关联的器件 UUID | ? |
| `setNetPortComponentUuid_IN` | `setNetPortComponentUuid_IN(component: { libraryUuid: string; uuid: string; } \| ILIB_DeviceItem \| ILIB_DeviceSearchItem): Promise<boolean>` | 设置在扩展 API 中 IN 网络端口关联的器件 UUID | ? |
| `setNetPortComponentUuid_OUT` | `setNetPortComponentUuid_OUT(component: { libraryUuid: string; uuid: string; } \| ILIB_DeviceItem \| ILIB_DeviceSearchItem): Promise<boolean>` | 设置在扩展 API 中 OUT 网络端口关联的器件 UUID | ? |
| `setNetPortComponentUuid_BI` | `setNetPortComponentUuid_BI(component: { libraryUuid: string; uuid: string; } \| ILIB_DeviceItem \| ILIB_DeviceSearchItem): Promise<boolean>` | 设置在扩展 API 中 BI 网络端口关联的器件 UUID | ? |
| `create` | `create(component: { libraryType?: ELIB_LibraryType.DEVICE; libraryUuid: string; uuid: string; } \| ILIB_DeviceItem \| ILIB_DeviceSearchItem \| { libraryType: ELIB_LibraryType.SYMBOL; libraryUuid: string; uuid: string; } \| ILIB_SymbolItem \| ILIB_SymbolSearchItem, x: number, y: number, subPartName?: string, rotation?: number, mirror?: boolean, addIntoBom?: boolean, addIntoPcb?: boolean): Promise<ISCH_PrimitiveComponent \| undefined>` | 创建器件 | ? |
| `createNetFlag` | `createNetFlag(identification: 'Power' \| 'Ground' \| 'AnalogGround' \| 'ProtectGround', net: string, x: number, y: number, rotation?: number, mirror?: boolean): Promise<ISCH_PrimitiveComponent \| undefined>` | 创建网络标识 | ? |
| `createNetPort` | `createNetPort(direction: 'IN' \| 'OUT' \| 'BI', net: string, x: number, y: number, rotation?: number, mirror?: boolean): Promise<ISCH_PrimitiveComponent \| undefined>` | 创建网络端口 | ? |
| `createShortCircuitFlag` | `createShortCircuitFlag(x: number, y: number, rotation?: number, mirror?: boolean): Promise<ISCH_PrimitiveComponent \| undefined>` | 创建短接标识 | ? |
| `createCbbSymbol` | `createCbbSymbol(cbbSymbol: { libraryUuid: string; cbbUuid: string; uuid?: string; }, x: number, y: number, rotation?: number, mirror?: boolean): Promise<ISCH_PrimitiveCbbSymbolComponent \| undefined>` | 创建复用模块符号 | ? |
| `placeCbbSchematicPage` | `placeCbbSchematicPage(cbbSchematicPage: { libraryUuid: string; cbbUuid: string; uuid: string; }, x: number, y: number): Promise<boolean>` | 放置复用模块原理图图页 | ? |
| `delete` | `delete(primitiveIds: string \| ISCH_PrimitiveComponent \| Array<string> \| Array<ISCH_PrimitiveComponent>): Promise<boolean>` | 删除器件 | ? |
| `modify` | `modify(primitiveId: string \| ISCH_PrimitiveComponent, property: { x?: number; y?: number; rotation?: number; mirror?: boolean; addIntoBom?: boolean; addIntoPcb?: boolean; designator?: string \| null; name?: string \| null; uniqueId?: string \| null; manufacturer?: string \| null; manufacturerId?: string \| null; supplier?: string \| null; supplierId?: string \| null; otherProperty?: { [key: string]: string \| number \| boolean; }; }): Promise<ISCH_PrimitiveComponent \| undefined>` | 修改器件 | ? |
| `get` | `get(primitiveIds: string): Promise<ISCH_PrimitiveComponent \| undefined>` | 获取器件 | ? |
| `get` | `get(primitiveIds: Array<string>): Promise<Array<ISCH_PrimitiveComponent>>` | 获取器件 | ? |
| `getAllPrimitiveId` | `getAllPrimitiveId(componentType?: ESCH_PrimitiveComponentType, allSchematicPages?: boolean): Promise<Array<string>>` | 获取所有器件的图元 ID | ? |
| `getAll` | `getAll(componentType?: ESCH_PrimitiveComponentType, allSchematicPages?: boolean): Promise<Array<ISCH_PrimitiveComponent>>` | 获取所有器件 | ? |
| `getAllPinsByPrimitiveId` | `getAllPinsByPrimitiveId(primitiveId: string): Promise<Array<ISCH_PrimitiveComponentPin> \| undefined>` | 获取器件关联的所有引脚 | ? |
| `placeComponentWithMouse` | `placeComponentWithMouse(component: { libraryUuid: string; uuid: string; } \| ILIB_DeviceItem \| ILIB_DeviceSearchItem, subPartName?: string): Promise<boolean>` | 使用鼠标放置器件 | ? |
| `placeSymbolWithMouse` | `placeSymbolWithMouse(symbol: { libraryUuid: string; uuid: string; } \| ILIB_SymbolItem \| ILIB_SymbolSearchItem, subPartName?: string, properties?: { [key: string]: boolean \| number \| string \| undefined; }): Promise<boolean>` | 使用鼠标放置符号 | ? |
| `getAllPropertyNames` | `getAllPropertyNames(): Promise<Array<string>>` | 获取所有器件的所有属性名称集合 | ? |

### `sch_PrimitiveObject` · SCH_PrimitiveObject （live 可达 7/7）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `create` | `create(content: File \| string, startX: number, startY: number, width?: number, height?: number, rotation?: number, mirror?: boolean, fileName?: string): Promise<ISCH_PrimitiveObject \| undefined>` | 创建二进制内嵌对象 | ✓ |
| `delete` | `delete(primitiveIds: string \| ISCH_PrimitiveObject \| Array<string> \| Array<ISCH_PrimitiveObject>): Promise<boolean>` | 删除二进制内嵌对象 | ✓ |
| `modify` | `modify(primitiveId: string \| ISCH_PrimitiveObject, property: { content?: File \| string; startX?: number; startY?: number; width?: number; height?: number; rotation?: number; mirror?: boolean; fileName?: string; }): Promise<ISCH_PrimitiveObject \| undefined>` | 修改二进制内嵌对象 | ✓ |
| `get` | `get(primitiveIds: string): Promise<ISCH_PrimitiveObject \| undefined>` | 获取二进制内嵌对象 | ✓ |
| `get` | `get(primitiveIds: Array<string>): Promise<Array<ISCH_PrimitiveObject>>` | 获取二进制内嵌对象 | ✓ |
| `getAllPrimitiveId` | `getAllPrimitiveId(): Promise<Array<string>>` | 获取所有二进制内嵌对象的图元 ID | ✓ |
| `getAll` | `getAll(): Promise<Array<ISCH_PrimitiveObject>>` | 获取所有二进制内嵌对象 | ✓ |

### `sch_PrimitivePin` · SCH_PrimitivePin （live 可达 7/7）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `create` | `create(x: number, y: number, pinNumber: string, pinName?: string, rotation?: number, pinLength?: number, pinColor?: string \| null, pinShape?: ESCH_PrimitivePinShape, pinType?: ESCH_PrimitivePinType): Promise<ISCH_PrimitivePin \| undefined>` | 创建引脚 | ✓ |
| `delete` | `delete(primitiveIds: string \| ISCH_PrimitivePin \| Array<string> \| Array<ISCH_PrimitivePin>): Promise<boolean>` | 删除引脚 | ✓ |
| `modify` | `modify(primitiveId: string \| ISCH_PrimitivePin \| ISCH_PrimitiveComponentPin, property: { x?: number; y?: number; pinNumber?: string; pinName?: string; rotation?: number; pinLength?: number; pinColor?: string \| null; pinShape?: ESCH_PrimitivePinShape; pinType?: ESCH_PrimitivePinType; }): Promise<ISCH_PrimitivePin \| ISCH_PrimitiveComponentPin \| undefined>` | 修改引脚 | ✓ |
| `get` | `get(primitiveIds: string): Promise<ISCH_PrimitivePin \| ISCH_PrimitiveComponentPin \| undefined>` | 获取引脚 | ✓ |
| `get` | `get(primitiveIds: Array<string>): Promise<Array<ISCH_PrimitivePin \| ISCH_PrimitiveComponentPin>>` | 获取引脚 | ✓ |
| `getAllPrimitiveId` | `getAllPrimitiveId(): Promise<Array<string>>` | 获取所有引脚的图元 ID | ✓ |
| `getAll` | `getAll(): Promise<Array<ISCH_PrimitivePin>>` | 获取所有引脚 | ✓ |

### `sch_PrimitivePolygon` · SCH_PrimitivePolygon （live 可达 7/7）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `create` | `create(line: Array<number>, color?: string \| null, fillColor?: string \| null, lineWidth?: number \| null, lineType?: ESCH_PrimitiveLineType \| null): Promise<ISCH_PrimitivePolygon \| undefined>` | 创建多边形 | ✓ |
| `delete` | `delete(primitiveIds: string \| ISCH_PrimitivePolygon \| Array<string> \| Array<ISCH_PrimitivePolygon>): Promise<boolean>` | 删除多边形 | ✓ |
| `modify` | `modify(primitiveId: string \| ISCH_PrimitivePolygon, property: { line?: Array<number>; color?: string \| null; fillColor?: string \| null; lineWidth?: number \| null; lineType?: ESCH_PrimitiveLineType \| null; }): Promise<ISCH_PrimitivePolygon \| undefined>` | 修改多边形 | ✓ |
| `get` | `get(primitiveIds: string): Promise<ISCH_PrimitivePolygon \| undefined>` | 获取多边形 | ✓ |
| `get` | `get(primitiveIds: Array<string>): Promise<Array<ISCH_PrimitivePolygon>>` | 获取多边形 | ✓ |
| `getAllPrimitiveId` | `getAllPrimitiveId(): Promise<Array<string>>` | 获取所有多边形的图元 ID | ✓ |
| `getAll` | `getAll(): Promise<Array<ISCH_PrimitivePolygon>>` | 获取所有多边形 | ✓ |

### `sch_PrimitiveRectangle` · SCH_PrimitiveRectangle （live 可达 7/7）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `create` | `create(topLeftX: number, topLeftY: number, width: number, height: number, cornerRadius?: number, rotation?: number, color?: string \| null, fillColor?: string \| null, lineWidth?: number \| null, lineType?: ESCH_PrimitiveLineType \| null, fillStyle?: ESCH_PrimitiveFillStyle \| null): Promise<ISCH_PrimitiveRectangle \| undefined>` | 创建矩形 | ✓ |
| `delete` | `delete(primitiveIds: string \| ISCH_PrimitiveRectangle \| Array<string> \| Array<ISCH_PrimitiveRectangle>): Promise<boolean>` | 删除矩形 | ✓ |
| `modify` | `modify(primitiveId: string \| ISCH_PrimitiveRectangle, property: { topLeftX?: number; topLeftY?: number; width?: number; height?: number; cornerRadius?: number; rotation?: number; color?: string \| null; fillColor?: string \| null; lineWidth?: number \| null; lineType?: ESCH_PrimitiveLineType \| null; fillStyle?: ESCH_PrimitiveFillStyle \| null; }): Promise<ISCH_PrimitiveRectangle \| undefined>` | 修改矩形 | ✓ |
| `get` | `get(primitiveIds: string): Promise<ISCH_PrimitiveRectangle \| undefined>` | 获取矩形 | ✓ |
| `get` | `get(primitiveIds: Array<string>): Promise<Array<ISCH_PrimitiveRectangle>>` | 获取矩形 | ✓ |
| `getAllPrimitiveId` | `getAllPrimitiveId(): Promise<Array<string>>` | 获取所有矩形的图元 ID | ✓ |
| `getAll` | `getAll(): Promise<Array<ISCH_PrimitiveRectangle>>` | 获取所有矩形 | ✓ |

### `sch_PrimitiveText` · SCH_PrimitiveText （live 可达 7/7）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `create` | `create(x: number, y: number, content: string, rotation?: number, textColor?: string \| null, fontName?: string \| null, fontSize?: number \| null, bold?: boolean, italic?: boolean, underLine?: boolean, alignMode?: ESCH_PrimitiveTextAlignMode): Promise<ISCH_PrimitiveText \| undefined>` | 创建文本 | ✓ |
| `delete` | `delete(primitiveIds: string \| ISCH_PrimitiveText \| Array<string> \| Array<ISCH_PrimitiveText>): Promise<boolean>` | 删除文本 | ✓ |
| `modify` | `modify(primitiveId: string \| ISCH_PrimitiveText, property: { x?: number; y?: number; content?: string; rotation?: number; textColor?: string \| null; fontName?: string \| null; fontSize?: number \| null; bold?: boolean; italic?: boolean; underLine?: boolean; alignMode?: ESCH_PrimitiveTextAlignMode; }): Promise<ISCH_PrimitiveText \| undefined>` | 修改文本 | ✓ |
| `get` | `get(primitiveIds: string): Promise<ISCH_PrimitiveText \| undefined>` | 获取文本 | ✓ |
| `get` | `get(primitiveIds: Array<string>): Promise<Array<ISCH_PrimitiveText>>` | 获取文本 | ✓ |
| `getAllPrimitiveId` | `getAllPrimitiveId(): Promise<Array<string>>` | 获取所有文本的图元 ID | ✓ |
| `getAll` | `getAll(): Promise<Array<ISCH_PrimitiveText>>` | 获取所有文本 | ✓ |

### `sch_PrimitiveWire` · SCH_PrimitiveWire （live 可达 7/7）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `create` | `create(line: Array<number> \| Array<Array<number>>, net?: string, color?: string \| null, lineWidth?: number \| null, lineType?: ESCH_PrimitiveLineType \| null): Promise<ISCH_PrimitiveWire \| undefined>` | 创建导线 | ✓ |
| `delete` | `delete(primitiveIds: string \| ISCH_PrimitiveWire \| Array<string> \| Array<ISCH_PrimitiveWire>): Promise<boolean>` | 删除导线 | ✓ |
| `modify` | `modify(primitiveId: string \| ISCH_PrimitiveWire, property: { line?: Array<number> \| Array<Array<number>>; net?: string; color?: string \| null; lineWidth?: number \| null; lineType?: ESCH_PrimitiveLineType \| null; }): Promise<ISCH_PrimitiveWire \| undefined>` | 修改导线 | ✓ |
| `get` | `get(primitiveIds: string): Promise<ISCH_PrimitiveWire \| undefined>` | 获取导线 | ✓ |
| `get` | `get(primitiveIds: Array<string>): Promise<Array<ISCH_PrimitiveWire>>` | 获取导线 | ✓ |
| `getAllPrimitiveId` | `getAllPrimitiveId(net?: string \| Array<string>): Promise<Array<string>>` | 获取所有导线的图元 ID | ✓ |
| `getAll` | `getAll(net?: string \| Array<string>): Promise<Array<ISCH_PrimitiveWire>>` | 获取所有导线 | ✓ |

### `sch_SelectControl` · SCH_SelectControl （live 可达 8/8）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `getAllSelectedPrimitives_PrimitiveId` | `getAllSelectedPrimitives_PrimitiveId(): Promise<Array<string>>` | 查询所有已选中图元的图元 ID | ✓ |
| `getAllSelectedPrimitives` | `getAllSelectedPrimitives(): Promise<Array<ISCH_Primitive>>` | 查询所有已选中图元的图元对象 | ✓ |
| `getSelectedPrimitives_PrimitiveId` | `getSelectedPrimitives_PrimitiveId(): Promise<Array<string>>` | 查询选中图元的图元 ID | ✓ |
| `getSelectedPrimitives` | `getSelectedPrimitives(): Promise<Array<Object>>` | 查询选中图元的所有参数 | ✓ |
| `doSelectPrimitives` | `doSelectPrimitives(primitiveIds: string \| Array<string>): Promise<boolean>` | 使用图元 ID 选中图元 | ✓ |
| `doCrossProbeSelect` | `doCrossProbeSelect(components?: Array<string>, pins?: Array<string>, nets?: Array<string>, highlight?: boolean, select?: boolean): boolean` | 进行交叉选择 | ✓ |
| `clearSelected` | `clearSelected(): boolean` | 清除选中 | ✓ |
| `getCurrentMousePosition` | `getCurrentMousePosition(): Promise<{ x: number; y: number; } \| undefined>` | 获取当前鼠标在画布上的位置 | ✓ |

### `sch_SimulationEngine` · SCH_SimulationEngine （live 可达 1/1）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `pushData` | `pushData(eventType: ESCH_DynamicSimulationEnginePushEventType \| ESCH_SpiceSimulationEnginePushEventType, props: { [key: string]: any; }): void` | 向仿真内核发送数据 | ✓ |

### `sch_Utils` · SCH_Utils （live 可达 1/1）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `splitLines` | `splitLines(lines: Array<number \| Array<number>>): Array<Array<number \| Array<number>>> \| undefined` | 拆分多段线 | ✓ |

## PNL · 拼板

### `pnl_Document` · PNL_Document （live 可达 1/1）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `save` | `save(): Promise<boolean>` | 保存文档 | ✓ |

## SYS · 系统（文件/对话框/存储/环境/消息/窗口/单位…）

### `sys_ClientUrl` · SYS_ClientUrl （live 可达 1/1）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `request` | `request(url: string, method?: 'GET' \| 'POST' \| 'HEAD' \| 'PUT' \| 'DELETE' \| 'PATCH', data?: string \| Blob \| FormData \| URLSearchParams, options?: { headers?: { [header: string]: any; }; integrity?: string; }, succeedCallFn?: (data: Response) => void \| Promise<void>): Promise<Response>` | 发起即时请求 | ✓ |

### `sys_Dialog` · SYS_Dialog （live 可达 7/7）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `createReactComponentizationDialogInterface` | `createReactComponentizationDialogInterface(React: ISYS_ReactComponentizationDialogReactInstance, Reconciler: ISYS_ReactComponentizationDialogReconcilerInstance): Promise<ISYS_ReactComponentizationDialogInterface>` | 创建 React 组件化弹出窗口接口 | ✓ |
| `showInformationMessage` | `showInformationMessage(content: string, title?: string, buttonTitle?: string): void` | 弹出消息窗口 | ✓ |
| `showConfirmationMessage` | `showConfirmationMessage(content: string, title?: string, mainButtonTitle?: string, buttonTitle?: string, callbackFn?: (mainButtonClicked: boolean) => void): void` | 弹出确认窗口 | ✓ |
| `showInputDialog` | `showInputDialog(beforeContent?: string, afterContent?: string, title?: string, type?: 'color' \| 'date' \| 'datetime-local' \| 'email' \| 'mouth' \| 'number' \| 'password' \| 'tel' \| 'text' \| 'time' \| 'url' \| 'week', value?: string \| number, otherProperty?: { max?: number; maxlength?: number; min?: number; minlength?: number; multiple?: boolean; pattern?: RegExp; placeholder?: string; readonly?: boolean; step?: number; }, callbackFn?: (value: any) => void): void` | 弹出输入窗口 | ✓ |
| `showSelectDialog` | `showSelectDialog(options: Array<string> \| Array<{ value: string; displayContent: string; }>, beforeContent?: string, afterContent?: string, title?: string, defaultOption?: string, multiple?: false, callbackFn?: (value: string) => void \| Promise<void>): void` | 弹出选择窗口 | ✓ |
| `showSelectDialog` | `showSelectDialog(options: Array<string> \| Array<{ value: string; displayContent: string; }>, beforeContent?: string, afterContent?: string, title?: string, defaultOption?: Array<string>, multiple?: true, callbackFn?: (value: Array<string>) => void \| Promise<void>): void` | 弹出多选窗口 | ✓ |
| `insertScriptToDialog` | `insertScriptToDialog(dialogId: string, scriptFunction: (...args: Array<any>) => void \| Promise<void>, ...args: Array<any>): void` | 向指定原生弹窗注入函数 | ✓ |

### `sys_Environment` · SYS_Environment （live 可达 12/12）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `isWeb` | `isWeb(): boolean` | 是否处于浏览器环境 | ✓ |
| `isClient` | `isClient(): boolean` | 是否处于客户端环境 | ✓ |
| `isEasyEDAProEdition` | `isEasyEDAProEdition(): boolean` | 是否为 EasyEDA Pro 版本 | ✓ |
| `isJLCEDAProEdition` | `isJLCEDAProEdition(): boolean` | 是否为 嘉立创EDA 专业版本 | ✓ |
| `isProPrivateEdition` | `isProPrivateEdition(): boolean` | 是否为私有化部署版本 | ✓ |
| `isOnlineMode` | `isOnlineMode(): boolean` | 是否为在线模式 | ✓ |
| `isHalfOfflineMode` | `isHalfOfflineMode(): boolean` | 是否为半离线模式 | ✓ |
| `isOfflineMode` | `isOfflineMode(): boolean` | 是否为全离线模式 | ✓ |
| `getEditorCurrentVersion` | `getEditorCurrentVersion(): string` | 获取编辑器当前版本 | ✓ |
| `getEditorCompliedDate` | `getEditorCompliedDate(): string` | 获取编辑器编译日期 | ✓ |
| `getUserInfo` | `getUserInfo(): { username?: string; nickname?: string; avatar?: string; uuid?: string; customerCode?: string; }` | 获取用户信息 | ✓ |
| `setKeepProjectHasOnlyOneBoard` | `setKeepProjectHasOnlyOneBoard(status?: boolean): Promise<void>` | 设置环境：保持工程仅拥有一个板子 | ✓ |

### `sys_FileManager` · SYS_FileManager （live 可达 15/15）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `getProjectFile` | `getProjectFile(fileName?: string, password?: string, fileType?: 'epro' \| 'epro2'): Promise<File \| undefined>` | 获取工程文件 | ✓ |
| `getDocumentFile` | `getDocumentFile(fileName?: string, password?: string, fileType?: 'epro' \| 'epro2'): Promise<File \| undefined>` | 获取文档文件 | ✓ |
| `getDocumentSource` | `getDocumentSource(): Promise<string \| undefined>` | 获取文档源码 | ✓ |
| `getDocumentFootprintSources` | `getDocumentFootprintSources(): Promise<Array<{ footprintUuid: string; documentSource: string; }>>` | 获取文档封装源码 | ✓ |
| `setDocumentSource` | `setDocumentSource(source: string): Promise<boolean>` | 修改文档源码 | ✓ |
| `getProjectFileByProjectUuid` | `getProjectFileByProjectUuid(projectUuid: string, fileName?: string, password?: string, fileType?: 'epro' \| 'epro2'): Promise<File \| undefined>` | 使用工程 UUID 获取工程文件 | ✓ |
| `getDeviceFileByDeviceUuid` | `getDeviceFileByDeviceUuid(deviceUuid: string \| Array<string>, libraryUuid?: string, fileType?: 'elibz' \| 'elibz2'): Promise<File \| undefined>` | 使用器件 UUID 获取器件文件 | ✓ |
| `getSymbolFileBySymbolUuid` | `getSymbolFileBySymbolUuid(symbolUuid: string \| Array<string>, libraryUuid?: string, fileType?: 'elibz' \| 'elibz2'): Promise<File \| undefined>` | 使用符号 UUID 获取符号文件 | ✓ |
| `getFootprintFileByFootprintUuid` | `getFootprintFileByFootprintUuid(footprintUuid: string \| Array<string>, libraryUuid?: string, fileType?: 'elibz' \| 'elibz2'): Promise<File \| undefined>` | 使用封装 UUID 获取封装文件 | ✓ |
| `getCbbFileByCbbUuid` | `getCbbFileByCbbUuid(cbbUuid: string, libraryUuid?: string, props?: { fileName?: string; password?: string; fileType?: 'epro' \| 'epro2'; templateSchematicUuid?: string; templatePcbUuid?: string; }): Promise<File \| undefined>` | 使用复用模块 UUID 获取复用模块文件 | ✓ |
| `getPanelLibraryFileByPanelLibraryUuid` | `getPanelLibraryFileByPanelLibraryUuid(panelLibraryUuid: string \| Array<string>, libraryUuid?: string, fileType?: 'elibz' \| 'elibz2'): Promise<File \| undefined>` | 使用面板库 UUID 获取面板库文件 | ✓ |
| `importProjectByProjectFile` | `importProjectByProjectFile(projectFile: File, fileType?: 'JLCEDA' \| 'JLCEDA Pro' \| 'EasyEDA' \| 'EasyEDA Pro' \| 'Allegro' \| 'OrCAD' \| 'EAGLE' \| 'KiCad' \| 'PADS' \| 'LTspice', props?: { importOption?: ESYS_ImportProjectImportOption; schematicObjectStyle?: ESYS_ImportProjectSchematicObjectStyle; associateFootprint?: boolean; associate3DModel?: boolean; importFootprintNotesLayer?: boolean; }, saveTo?: { operation: 'New Project'; newProjectOwnerTeamUuid: IDMT_TeamItem['uuid']; newProjectOwnerFolderUuid?: IDMT_FolderItem['uuid']; newProjectName?: string; newProjectFriendlyName?: string; newProjectDescription?: string; newProjectCollaborationMode?: EDMT_ProjectCollaborationMode; } \| { operation: 'Existing Project'; existingProjectUuid: IDMT_BriefProjectItem['uuid']; }, librariesImportSetting?: { ownerTeamUuid: IDMT_TeamItem['uuid']; deviceClassification?: Array<string>; symbolClassification?: Array<string>; footprintClassification?: Array<string>; createDeviceForSingleSymbol?: boolean; updateExistingLibrariesWithTheSameName?: boolean; }): Promise<IDMT_BriefProjectItem \| undefined>` | 使用工程文件导入工程 | ✓ |
| `importProjectByProjectFile` | `importProjectByProjectFile(projectFile: File, fileType?: 'Altium Designer' \| 'Protel', props?: { importOption?: ESYS_ImportProjectImportOption; viaSolderMaskExpansion?: ESYS_ImportProjectViaSolderMaskExpansion; boardOutlineSource?: ESYS_ImportProjectBoardOutlineSource; schematicObjectStyle?: ESYS_ImportProjectSchematicObjectStyle; associateFootprint?: boolean; associate3DModel?: boolean; importFootprintNotesLayer?: boolean; }, saveTo?: { operation: 'New Project'; newProjectOwnerTeamUuid: IDMT_TeamItem['uuid']; newProjectOwnerFolderUuid?: IDMT_FolderItem['uuid']; newProjectName?: string; newProjectFriendlyName?: string; newProjectDescription?: string; newProjectCollaborationMode?: EDMT_ProjectCollaborationMode; } \| { operation: 'Existing Project'; existingProjectUuid: IDMT_BriefProjectItem['uuid']; }, librariesImportSetting?: { ownerTeamUuid: IDMT_TeamItem['uuid']; deviceClassification?: Array<string>; symbolClassification?: Array<string>; footprintClassification?: Array<string>; createDeviceForSingleSymbol?: boolean; updateExistingLibrariesWithTheSameName?: boolean; }): Promise<IDMT_BriefProjectItem \| undefined>` | 使用工程文件导入工程 | ✓ |
| `extractProjectInfo` | `extractProjectInfo(data: File): Promise<any>` | 提取文件内的工程配置信息 | ✓ |
| `extractLibInfo` | `extractLibInfo(data: File \| Array<File>): Promise<any>` | 提取文件内的库配置信息 | ✓ |

### `sys_FileSystem` · SYS_FileSystem （live 可达 13/13）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `getExtensionFile` | `getExtensionFile(uri: string): Promise<File \| undefined>` | 获取扩展内的文件 | ✓ |
| `openReadFileDialog` | `openReadFileDialog(filenameExtensions?: string \| Array<string>, multiFiles?: true): Promise<Array<File> \| undefined>` | 打开读入文件窗口 | ✓ |
| `openReadFileDialog` | `openReadFileDialog(filenameExtensions?: string \| Array<string>, multiFiles?: false): Promise<File \| undefined>` | 打开读入文件窗口 | ✓ |
| `openReadFolderDialog` | `openReadFolderDialog(): Promise<Array<{ relativePath: string; file: File; }>>` | 打开读入文件夹窗口 | ✓ |
| `saveFile` | `saveFile(fileData: File \| Blob, fileName?: string): Promise<void>` | 保存文件 | ✓ |
| `readFileFromFileSystem` | `readFileFromFileSystem(uri: string): Promise<File \| undefined>` | 从文件系统读取文件 | ✓ |
| `saveFileToFileSystem` | `saveFileToFileSystem(uri: string, fileData: File \| Blob, fileName?: string, force?: boolean): Promise<boolean>` | 向文件系统写入文件 | ✓ |
| `listFilesOfFileSystem` | `listFilesOfFileSystem(folderPath: string, recursive?: boolean): Promise<Array<ISYS_FileSystemFileList>>` | 查看文件系统路径下的文件列表 | ✓ |
| `deleteFileInFileSystem` | `deleteFileInFileSystem(uri: string, force?: boolean): Promise<boolean>` | 删除文件系统内的文件 | ✓ |
| `getEdaPath` | `getEdaPath(): Promise<string>` | 获取 EDA 文档目录路径 | ✓ |
| `getDocumentsPath` | `getDocumentsPath(): Promise<string>` | 获取文档目录路径 | ✓ |
| `getLibrariesPaths` | `getLibrariesPaths(): Promise<Array<string>>` | 获取库目录路径 | ✓ |
| `getProjectsPaths` | `getProjectsPaths(): Promise<Array<string>>` | 获取工程目录路径 | ✓ |

### `sys_FontManager` · SYS_FontManager （live 可达 3/3）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `getFontsList` | `getFontsList(): Promise<Array<string>>` | 获取当前已经配置的字体列表 | ✓ |
| `addFont` | `addFont(fontName: string): Promise<boolean>` | 添加字体到字体列表 | ✓ |
| `deleteFont` | `deleteFont(fontName: string): Promise<boolean>` | 删除字体列表内的指定字体 | ✓ |

### `sys_FormatConversion` · SYS_FormatConversion （live 可达 4/4）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `convertAltiumDesignerLibrariesToEasyEDASingleFile` | `convertAltiumDesignerLibrariesToEasyEDASingleFile(file: File \| Array<File>): Promise<File \| undefined>` | 转换 Altium Designer 库到单个嘉立创库文件 | ✓ |
| `convertAltiumDesignerLibrariesToEasyEDAMultiFiles` | `convertAltiumDesignerLibrariesToEasyEDAMultiFiles(file: File \| Array<File>): Promise<Array<File>>` | 转换 Altium Designer 库到多个嘉立创库文件（每个器件一个文件） | ✓ |
| `convertDisaLibrariesToEasyEDASingleFile` | `convertDisaLibrariesToEasyEDASingleFile(file: File \| Array<File>): Promise<File \| undefined>` | 转换 T/DISA 4001 库到单个嘉立创库文件 | ✓ |
| `convertDisaLibrariesToEasyEDAMultiFiles` | `convertDisaLibrariesToEasyEDAMultiFiles(file: File \| Array<File>): Promise<Array<File>>` | 转换 T/DISA 4001 库到多个嘉立创库文件（每个器件一个文件） | ✓ |

### `sys_HeaderMenu` · SYS_HeaderMenu （live 可达 6/6）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `insertHeaderMenus` | `insertHeaderMenus(headerMenus: ISYS_HeaderMenus): Promise<void>` | 导入顶部菜单数据 | ✓ |
| `removeHeaderMenus` | `removeHeaderMenus(): void` | 移除顶部菜单数据 | ✓ |
| `replaceHeaderMenus` | `replaceHeaderMenus(headerMenus: ISYS_HeaderMenus): Promise<void>` | 替换顶部菜单数据 | ✓ |
| `removeSystemHeaderMenuItem` | `removeSystemHeaderMenuItem(id: Array<string>, props?: { /** 是否移除前面的分隔线 */ removeTheBeforeDivider?: boolean; /** 是否移除后面的分隔线 */ removeTheAfterDivider?: boolean; }): Promise<boolean>` | 移除系统顶部菜单项 | ✓ |
| `insertSystemHeaderMenuItem` | `insertSystemHeaderMenuItem(env: ESYS_HeaderMenuEnvironment, id: Array<string>, props: { /** 菜单项的标题 */ title: string; /** 注册方法名称 */ registerFn?: string; /** 子菜单项 */ menuItems?: Array<ISYS_HeaderMenuSub1MenuItem \| ISYS_HeaderMenuSub2MenuItem \| null>; /** 是否在前面插入分隔线 */ insertDividerBefore?: boolean; /** 是否在后面插入分隔线 */ insertDividerAfter?: boolean; /** 在指定 ID 的菜单项的前面插入当前菜单项 */ insertBefore?: string; /** 在插入时如若指定的菜单项前面存在分隔线，是否跨过该分隔线（即和 insertBefore 指定 ID 的菜单项之间是否可能存在分隔线，这和 insertDividerAfter 并不冲突，因为 insertDividerAfter 在菜单项插入完成后添加） */ crossDividerWhenInsert?: boolean; }): Promise<string \| undefined>` | 在指定位置插入系统顶部菜单项 | ✓ |
| `insertSystemHeaderMenus` | `insertSystemHeaderMenus(headerMenus: ISYS_HeaderMenus): void` | 导入系统顶部菜单 **暂不开发** | ✓ |

### `sys_I18n` · SYS_I18n （live 可达 10/10）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `text` | `text(tag: string, namespace?: string, language?: string, ...args: Array<any>): string` | 输出语言文本 | ✓ |
| `getCurrentLanguage` | `getCurrentLanguage(): Promise<string>` | 获取当前语言环境 | ✓ |
| `getAllSupportedLanguages` | `getAllSupportedLanguages(): Array<string>` | 查询所有支持的语言 | ✓ |
| `isLanguageSupported` | `isLanguageSupported(language: string): boolean` | 检查语言是否受支持 | ✓ |
| `importMultilingual` | `importMultilingual(language: string, source: ISYS_LanguageKeyValuePairs): boolean` | 导入多语言 | ✓ |
| `importMultilingualLanguage` | `importMultilingualLanguage(namespace: string, language: string, source: ISYS_LanguageKeyValuePairs): boolean` | 导入多语言：指定命名空间和语言 | ✓ |
| `importMultilingualNamespace` | `importMultilingualNamespace(namespace: string, source: ISYS_MultilingualLanguagesData): boolean` | 导入多语言：指定命名空间 | ✓ |
| `addLanguageChangedEventListener` | `addLanguageChangedEventListener(id: string, callFn: (newLanguage: string, lastLanguage: string) => void \| Promise<void>, onlyOnce: boolean): void` | 新增语言切换事件监听 | ✓ |
| `removeEventListener` | `removeEventListener(id: string): boolean` | 移除事件监听 | ✓ |
| `isEventListenerAlreadyExist` | `isEventListenerAlreadyExist(id: string): boolean` | 查询事件监听是否存在 | ✓ |

### `sys_IFrame` · SYS_IFrame （live 可达 5/5）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `openIFrame` | `openIFrame(htmlFileName: string, width?: number, height?: number, id?: string, props?: { /** 是否显示最大化按钮 */ maximizeButton?: boolean; /** 是否显示最小化按钮 */ minimizeButton?: boolean; /** 最小化风格：折叠、收缩 */ minimizeStyle?: 'collapsed' \| 'constricted'; /** 按钮点击回调 */ buttonCallbackFn?: (button: 'close' \| 'minimize' \| 'maximize') => void \| Promise<void>; /** 关闭前回调：回调返回 `false` 时阻止按钮触发 */ onBeforeCloseCallFn?: () => boolean \| undefined \| Promise<boolean \| undefined>; /** 是否背景置灰 */ grayscaleMask?: boolean; /** IFrame 标题 */ title?: string; }): Promise<boolean>` | 打开内联框架窗口 | ✓ |
| `closeIFrame` | `closeIFrame(id?: string): Promise<boolean>` | 关闭内联框架窗口 | ✓ |
| `hideIFrame` | `hideIFrame(id?: string): Promise<boolean>` | 隐藏内联框架窗口 | ✓ |
| `showIFrame` | `showIFrame(id?: string): Promise<boolean>` | 显示内联框架窗口 | ✓ |
| `isIFrameAlreadyExist` | `isIFrameAlreadyExist(id: string): Promise<boolean>` | 内联框架是否已存在 | ✓ |

### `sys_LoadingAndProgressBar` · SYS_LoadingAndProgressBar （live 可达 4/4）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `showProgressBar` | `showProgressBar(progress?: number, title?: string): void` | 显示进度条或设置进度条进度 | ✓ |
| `destroyProgressBar` | `destroyProgressBar(): void` | 销毁进度条 | ✓ |
| `showLoading` | `showLoading(): void` | 显示无进度加载覆盖 | ✓ |
| `destroyLoading` | `destroyLoading(): void` | 销毁无进度加载覆盖 | ✓ |

### `sys_Log` · SYS_Log （live 可达 5/5）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `add` | `add(message: string, type?: ESYS_LogType): void` | 添加日志条目 | ✓ |
| `clear` | `clear(): void` | 清空日志 | ✓ |
| `export` | `export(types?: ESYS_LogType \| Array<ESYS_LogType>): void` | 导出日志 | ✓ |
| `sort` | `sort(types?: ESYS_LogType \| Array<ESYS_LogType>): Promise<Array<ISYS_LogLine>>` | 筛选并获取日志条目 | ✓ |
| `find` | `find(message: string \| Array<string \| { text: string; attr?: { id?: string; path?: string; sheet?: string; pcbid?: string; type?: string; }; }>, types?: ESYS_LogType \| Array<ESYS_LogType>): Promise<Array<ISYS_LogLine>>` | 查找条目 | ✓ |

### `sys_Message` · SYS_Message （live 可达 3/3）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `showToastMessage` | `showToastMessage(message: string, messageType?: ESYS_ToastMessageType, timer?: number, bottomPanel?: ESYS_BottomPanelTab, buttonTitle?: string, buttonCallbackFn?: string): void` | 显示吐司消息 | ✓ |
| `showFollowMouseTip` | `showFollowMouseTip(tip: string, msTimeout?: number): Promise<void>` | 展示跟随鼠标的提示 | ✓ |
| `removeFollowMouseTip` | `removeFollowMouseTip(tip?: string): Promise<void>` | 移除跟随鼠标的提示 | ✓ |

### `sys_MessageBox` · SYS_MessageBox （live 可达 2/2）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `showInformationMessage` | `showInformationMessage(content: string, title?: string, buttonTitle?: string): void` | 显示消息框 | ✓ |
| `showConfirmationMessage` | `showConfirmationMessage(content: string, title?: string, mainButtonTitle?: string, buttonTitle?: string, callbackFn?: (mainButtonClicked: boolean) => void): void` | 显示确认框 | ✓ |

### `sys_MessageBus` · SYS_MessageBus （live 可达 18/18）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `createPrivateMessageBus` | `createPrivateMessageBus(): void` | 创建私有消息总线 | ✓ |
| `removePrivateMessageBus` | `removePrivateMessageBus(): void` | 移除私有消息总线 | ✓ |
| `push` | `push(topic: string, message: any): void` | 私有消息总线：推消息 | ✓ |
| `pushPublic` | `pushPublic(topic: string, message: any): void` | 公共消息总线：推消息 | ✓ |
| `pull` | `pull(topic: string, callbackFn: (message: any) => void): ISYS_MessageBusTask` | 私有消息总线：拉消息 | ✓ |
| `pullPublic` | `pullPublic(topic: string, callbackFn: (message: any) => void): ISYS_MessageBusTask` | 公共消息总线：拉消息 | ✓ |
| `pullAsync` | `pullAsync(topic: string): Promise<any>` | 私有消息总线：拉消息 Promise 版本 | ✓ |
| `pullAsyncPublic` | `pullAsyncPublic(topic: string): Promise<any>` | 公共消息总线：拉消息 Promise 版本 | ✓ |
| `publish` | `publish(topic: string, message: any): void` | 私有消息总线：发布消息 | ✓ |
| `publishPublic` | `publishPublic(topic: string, message: any): void` | 公共消息总线：发布消息 | ✓ |
| `subscribe` | `subscribe(topic: string, callbackFn: (message: any) => void): ISYS_MessageBusTask` | 私有消息总线：订阅消息 | ✓ |
| `subscribePublic` | `subscribePublic(topic: string, callbackFn: (message: any) => void): ISYS_MessageBusTask` | 公共消息总线：订阅消息 | ✓ |
| `subscribeOnce` | `subscribeOnce(topic: string, callbackFn: (message: any) => void): ISYS_MessageBusTask` | 私有消息总线：订阅单次消息 | ✓ |
| `subscribeOncePublic` | `subscribeOncePublic(topic: string, callbackFn: (message: any) => void): ISYS_MessageBusTask` | 公共消息总线：订阅单次消息 | ✓ |
| `rpcCall` | `rpcCall(topic: string, message?: any, timeout?: number): Promise<any>` | 私有消息总线：调用 RPC 服务 | ✓ |
| `rpcCallPublic` | `rpcCallPublic(topic: string, message?: any, timeout?: number): Promise<any>` | 公共消息总线：调用 RPC 服务 | ✓ |
| `rpcService` | `rpcService(topic: string, callbackFn: (...args: Array<any>) => any \| Promise<any>): void` | 私有消息总线：注册 RPC 服务 | ✓ |
| `rpcServicePublic` | `rpcServicePublic(topic: string, callbackFn: (...args: Array<any>) => any \| Promise<any>): void` | 公共消息总线：注册 RPC 服务 | ✓ |

### `sys_PanelControl` · SYS_PanelControl （live 可达 12/12）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `openLeftPanel` | `openLeftPanel(tab?: ESYS_LeftPanelTab): void` | 打开左侧面板 | ✓ |
| `closeLeftPanel` | `closeLeftPanel(): void` | 关闭左侧面板 | ✓ |
| `toggleLeftPanelLockState` | `toggleLeftPanelLockState(state?: boolean): void` | 切换左侧面板锁定状态 | ✓ |
| `isLeftPanelLocked` | `isLeftPanelLocked(): Promise<boolean>` | 查询左侧面板是否已锁定 | ✓ |
| `openRightPanel` | `openRightPanel(tab?: ESYS_RightPanelTab): void` | 打开右侧面板 | ✓ |
| `closeRightPanel` | `closeRightPanel(): void` | 关闭右侧面板 | ✓ |
| `toggleRightPanelLockState` | `toggleRightPanelLockState(state?: boolean): void` | 切换右侧面板锁定状态 | ✓ |
| `isRightPanelLocked` | `isRightPanelLocked(): Promise<boolean>` | 查询右侧面板是否已锁定 | ✓ |
| `openBottomPanel` | `openBottomPanel(tab?: ESYS_BottomPanelTab): void` | 打开底部面板 | ✓ |
| `closeBottomPanel` | `closeBottomPanel(): void` | 关闭底部面板 | ✓ |
| `toggleBottomPanelLockState` | `toggleBottomPanelLockState(state?: boolean): void` | 切换底部面板锁定状态 | ✓ |
| `isBottomPanelLocked` | `isBottomPanelLocked(): Promise<boolean>` | 查询底部面板是否已锁定 | ✓ |

### `sys_RightClickMenu` · SYS_RightClickMenu （live 可达 1/1）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `changeMenu` | `changeMenu(menuId: string, menuItems: Array<ISYS_RightClickMenuItem \| null>): Promise<void>` | 修改右键菜单 | ✓ |

### `sys_Setting` · SYS_Setting （live 可达 1/1）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `restoreDefault` | `restoreDefault(): Promise<boolean>` | 全局恢复默认设置 | ✓ |

### `sys_ShortcutKey` · SYS_ShortcutKey （live 可达 3/3）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `registerShortcutKey` | `registerShortcutKey(shortcutKey: TSYS_ShortcutKeys, title: string, callbackFn: (shortcutKey: TSYS_ShortcutKeys) => void \| Promise<void>, documentType?: Array<ESYS_ShortcutKeyEffectiveEditorDocumentType>, scene?: Array<ESYS_ShortcutKeyEffectiveEditorScene>): Promise<boolean>` | 注册快捷键 | ✓ |
| `unregisterShortcutKey` | `unregisterShortcutKey(shortcutKey: TSYS_ShortcutKeys): Promise<boolean>` | 反注册快捷键 | ✓ |
| `getShortcutKeys` | `getShortcutKeys(includeSystem?: boolean): Promise<Array<{ shortcutKey: TSYS_ShortcutKeys; title: string; documentType: Array<ESYS_ShortcutKeyEffectiveEditorDocumentType>; scene: Array<ESYS_ShortcutKeyEffectiveEditorScene>; }>>` | 查询快捷键列表 | ✓ |

### `sys_Storage` · SYS_Storage （live 可达 6/6）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `getExtensionAllUserConfigs` | `getExtensionAllUserConfigs(): { [key: string]: any; }` | 获取扩展所有用户配置 | ✓ |
| `setExtensionAllUserConfigs` | `setExtensionAllUserConfigs(configs: { [key: string]: any; }): Promise<boolean>` | 设置扩展所有用户配置 | ✓ |
| `clearExtensionAllUserConfigs` | `clearExtensionAllUserConfigs(): Promise<boolean>` | 清除扩展所有用户配置 | ✓ |
| `getExtensionUserConfig` | `getExtensionUserConfig(key: string): any \| undefined` | 获取扩展用户配置 | ✓ |
| `setExtensionUserConfig` | `setExtensionUserConfig(key: string, value: any): Promise<boolean>` | 设置扩展用户配置 | ✓ |
| `deleteExtensionUserConfig` | `deleteExtensionUserConfig(key: string): Promise<boolean>` | 删除扩展用户配置 | ✓ |

### `sys_Timer` · SYS_Timer （live 可达 4/4）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `setIntervalTimer` | `setIntervalTimer(id: string, timeout: number, callFn: (...args: any) => void, ...args: any): boolean` | 设置循环定时器 | ✓ |
| `clearIntervalTimer` | `clearIntervalTimer(id: string): boolean` | 清除指定循环定时器 | ✓ |
| `setTimeoutTimer` | `setTimeoutTimer(id: string, timeout: number, callFn: (...args: any) => void, ...args: any): boolean` | 设置单次定时器 | ✓ |
| `clearTimeoutTimer` | `clearTimeoutTimer(id: string): boolean` | 清除指定单次定时器 | ✓ |

### `sys_ToastMessage` · SYS_ToastMessage （live 可达 1/1）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `showMessage` | `showMessage(message: string, messageType?: ESYS_ToastMessageType, timer?: number, bottomPanel?: ESYS_BottomPanelTab, buttonTitle?: string, buttonCallbackFn?: string): void` | 显示吐司消息 | ✓ |

### `sys_Tool` · SYS_Tool （live 可达 3/3）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `netlistComparison` | `netlistComparison(netlist1: string \| { projectUuid: string; documentUuid: string; } \| File, netlist2: string \| { projectUuid: string; documentUuid: string; } \| File): Promise<Array<{ type: 'Net' \| 'Component'; object: string; netlist1Name: Array<string>; netlist2Name: Array<string>; }>>` | 网表对比 | ✓ |
| `schematicComparison` | `schematicComparison(schematic1: string \| { projectUuid: string; schematicUuid: string; } \| File, schematic2: string \| { projectUuid: string; schematicUuid: string; } \| File): Promise<any>` | 原理图对比 | ✓ |
| `pcbComparison` | `pcbComparison(pcb1: string \| { projectUuid: string; pcbUuid: string; } \| File, pcb2: string \| { projectUuid: string; pcbUuid: string; } \| File): Promise<any>` | PCB 对比 | ✓ |

### `sys_Unit` · SYS_Unit （live 可达 7/7）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `getFrontendDataUnit` | `getFrontendDataUnit(): Promise<ESYS_Unit \| undefined>` | 获取 EDA 前端数据单位跨度 | ✓ |
| `milToMm` | `milToMm(mil: number, numberOfDecimals?: number): number` | 单位转换：密尔到毫米 | ✓ |
| `milToInch` | `milToInch(mil: number, numberOfDecimals?: number): number` | 单位转换：密尔到英寸 | ✓ |
| `mmToMil` | `mmToMil(mm: number, numberOfDecimals?: number): number` | 单位转换：毫米到密尔 | ✓ |
| `mmToInch` | `mmToInch(mm: number, numberOfDecimals?: number): number` | 单位转换：毫米到英寸 | ✓ |
| `inchToMil` | `inchToMil(inch: number, numberOfDecimals?: number): number` | 单位转换：英寸到密尔 | ✓ |
| `inchToMm` | `inchToMm(inch: number, numberOfDecimals?: number): number` | 单位转换：英寸到毫米 | ✓ |

### `sys_WebSocket` · SYS_WebSocket （live 可达 3/3）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `register` | `register(id: string, serviceUri: string, receiveMessageCallFn?: (event: MessageEvent<any>) => void \| Promise<void>, connectedCallFn?: () => void \| Promise<void>, protocols?: string \| Array<string>): void` | 注册 WebSocket 连接 | ✓ |
| `send` | `send(id: string, data: string \| ArrayBuffer \| Blob \| ArrayBufferView, extensionUuid?: string): void` | 向 WebSocket 服务器发送数据 | ✓ |
| `close` | `close(id: string, code?: number, reason?: string, extensionUuid?: string): void` | 关闭 WebSocket 连接 | ✓ |

### `sys_Window` · SYS_Window （live 可达 9/9）

| 方法 | 签名 | 说明 | live |
|---|---|---|:--:|
| `open` | `open(url: string, target?: ESYS_WindowOpenTarget): void` | 打开资源窗口 | ✓ |
| `addEventListener` | `addEventListener(type: ESYS_WindowEventType, listener: (ev: any) => any, options?: { capture?: boolean; once?: boolean; passive?: boolean; signal?: AbortSignal; }): ISYS_WindowEventListenerRemovableObject \| undefined` | 新增事件监听 | ✓ |
| `removeEventListener` | `removeEventListener(removableObject: ISYS_WindowEventListenerRemovableObject): void` | 移除事件监听 | ✓ |
| `openUI` | `openUI(uiName: string, args?: { [key: string]: any; }): Promise<void>` | 打开 UI 窗口 | ✓ |
| `getCurrentTheme` | `getCurrentTheme(): Promise<ESYS_Theme>` | 获取当前主题 | ✓ |
| `getUrlParam` | `getUrlParam(key: string): string \| null` | 获取 URL 参数 | ✓ |
| `getUrlAnchor` | `getUrlAnchor(): string` | 获取 URL 锚点 | ✓ |
| `urlPushState` | `urlPushState(url: string): void` | 追加新的 URL 历史记录栈信息 | ✓ |
| `urlReplaceState` | `urlReplaceState(url: string): void` | 修改当前的 URL 历史记录栈信息 | ✓ |

## EDA · 根对象

### `eDA` · EDA （运行期未抽样）

_（无公开方法）_

## 词汇表 · 枚举（enum）

> 调用各方法时传参/解读返回值所需的合法取值集合（层 id、图元类型、库类型、单位…）。

### `CellContentType` — 单元格内容类型枚举 */

| 成员 | 值 |
|---|---|
| `TEXT` | `"TEXT"` |
| `INPUT` | `"INPUT"` |
| `TEXTAREA` | `"TEXTAREA"` |
| `SELECT` | `"SELECT"` |
| `CHECKBOX` | `"CHECKBOX"` |
| `CUSTOM` | `"CUSTOM"` |
| `UNDEFINED` | `"UNDEFINED"` |

### `CellType` — 单元格类型枚举 */

| 成员 | 值 |
|---|---|
| `TH` | `"th"` |
| `TD` | `"td"` |

### `EDMT_EditorDocumentType` — 编辑器文档类型

| 成员 | 值 |
|---|---|
| `HOME` | `-1` |
| `BLANK` | `0` |
| `PROJECT` | `5` |
| `SCHEMATIC_PAGE` | `1` |
| `PCB` | `3` |
| `PCB_2D_PREVIEW` | `12` |
| `PCB_3D_PREVIEW` | `15` |
| `PANEL` | `26` |
| `PANEL_3D_PREVIEW` | `27` |
| `SYMBOL_COMPONENT` | `2` |
| `SYMBOL_NET_FLAG` | `18` |
| `SYMBOL_NET_PORT` | `19` |
| `SYMBOL_DRAWING` | `20` |
| `SYMBOL_NON_ELECTRICAL` | `21` |
| `SYMBOL_SHORT_CIRCUIT_FLAG` | `22` |
| `SYMBOL_OFF_PAGE_CONNECTOR_FLAG` | `25` |
| `SYMBOL_CBB` | `17` |
| `FOOTPRINT` | `4` |
| `PANEL_LIBRARY` | `29` |
| `SIMULATION_SCHEMATIC_PAGE_NGSPICE` | `8` |
| `SIMULATION_SCHEMATIC_PAGE_SIMULIDE` | `9` |
| `SIMULATION_SYMBOL_COMPONENT_NGSPICE` | `7` |
| `SIMULATION_SYMBOL_COMPONENT_SIMULIDE` | `32` |

### `EDMT_EditorSplitScreenDirection` — 编辑器分屏方向

| 成员 | 值 |
|---|---|
| `HORIZONTAL` | `"horizontal"` |
| `VERTICAL` | `"vertical"` |

### `EDMT_EditorTabEventType` — 编辑器标签页事件类型

| 成员 | 值 |
|---|---|
| `TOGGLE` | `"toggle"` |
| `CLOSE` | `"close"` |
| `OPEN` | `"open"` |

### `EDMT_IndicatorMarkerType` — 指示标记类型

| 成员 | 值 |
|---|---|
| `POINT` | `"point"` |
| `CIRCLE` | `"circle"` |
| `LINE` | `"line"` |
| `ARC` | `"arc"` |
| `RECTANGLE` | `"rectangle"` |

### `EDMT_ItemType` — 文档树项目类型

| 成员 | 值 |
|---|---|
| `WORKSPACE` | `"Workspace"` |
| `TEAM` | `"Team"` |
| `FOLDER` | `"Folder"` |
| `PROJECT` | `"Project"` |
| `CBB_PROJECT` | `"CBB Project"` |
| `BOARD` | `"Board"` |
| `SCHEMATIC` | `"Schematic"` |
| `CBB_SCHEMATIC` | `"CBB Schematic"` |
| `SCHEMATIC_PAGE` | `"Schematic Page"` |
| `PCB` | `"PCB"` |
| `CBB_PCB` | `"CBB PCB"` |
| `PANEL` | `"Panel"` |

### `EDMT_ProjectCollaborationMode` — 工程协作模式

| 成员 | 值 |
|---|---|
| `STRICT` | `3` |
| `FREE` | `1` |

### `ELIB_DeviceJlcLibraryCategory` — 嘉立创贴片库类别

| 成员 | 值 |
|---|---|
| `STANDARD` | `"standard"` |
| `EXTEND` | `"extend"` |

### `ELIB_LibraryType` — 综合库库类型

| 成员 | 值 |
|---|---|
| `DEVICE` | `"3"` |
| `SYMBOL` | `"2"` |
| `FOOTPRINT` | `"4"` |
| `CBB` | `"1"` |
| `MODEL` | `"5"` |
| `PANEL_LIBRARY` | `"29"` |

### `ELIB_PreviewType` — 预览视图类型

| 成员 | 值 |
|---|---|
| `SYMBOL` | `"S"` |
| `FOOTPRINT` | `"F"` |
| `PRODUCT` | `"P"` |
| `MODEL_3D` | `"3D"` |

### `ELIB_SymbolType` — 符号类型

| 成员 | 值 |
|---|---|
| `COMPONENT` | `2` |
| `NET_FLAG` | `18` |
| `NET_PORT` | `19` |
| `DRAWING` | `20` |
| `NON_ELECTRICAL` | `21` |
| `SHORT_CIRCUIT_FLAG` | `22` |
| `OFF_PAGE_CONNECTOR` | `25` |
| `DIFFERENTIAL_PAIRS_FLAG` | `31` |
| `CBB_SYMBOL` | `17` |

### `EPCB_DocumentRatlineCalculatingActiveStatus` — 文档飞线计算功能状态

| 成员 | 值 |
|---|---|
| `ACTIVE` | `"active"` |
| `INACTIVE` | `"inactive"` |

### `EPCB_InactiveLayerDisplayMode` — 非激活层展示模式

| 成员 | 值 |
|---|---|
| `NORMAL_BRIGHTNESS` | `0` |
| `TURN_GRAY` | `1` |
| `HIDE` | `2` |

### `EPCB_LayerColorConfiguration` — 图层颜色配置

| 成员 | 值 |
|---|---|
| `JLCEDA` | `1` |
| `EASYEDA` | `1` |
| `ALTIUM_DESIGNER` | `2` |
| `PADS` | `3` |
| `KICAD` | `4` |

### `EPCB_LayerId` — 图层 ID

| 成员 | 值 |
|---|---|
| `TOP` | `1` |
| `TOP_SILKSCREEN` | `3` |
| `TOP_SOLDER_MASK` | `5` |
| `TOP_PASTE_MASK` | `7` |
| `TOP_ASSEMBLY` | `9` |
| `TOP_STIFFENER` | `58` |
| `BOTTOM` | `2` |
| `BOTTOM_SILKSCREEN` | `4` |
| `BOTTOM_SOLDER_MASK` | `6` |
| `BOTTOM_PASTE_MASK` | `8` |
| `BOTTOM_ASSEMBLY` | `10` |
| `BOTTOM_STIFFENER` | `59` |
| `BOARD_OUTLINE` | `11` |
| `MULTI` | `12` |
| `DOCUMENT` | `13` |
| `MECHANICAL` | `14` |
| `RATLINE` | `57` |
| `INNER_1` | `15` |
| `INNER_2` | `16` |
| `INNER_3` | `17` |
| `INNER_4` | `18` |
| `INNER_5` | `19` |
| `INNER_6` | `20` |
| `INNER_7` | `21` |
| `INNER_8` | `22` |
| `INNER_9` | `23` |
| `INNER_10` | `24` |
| `INNER_11` | `25` |
| `INNER_12` | `26` |
| `INNER_13` | `27` |
| `INNER_14` | `28` |
| `INNER_15` | `29` |
| `INNER_16` | `30` |
| `INNER_17` | `31` |
| `INNER_18` | `32` |
| `INNER_19` | `33` |
| `INNER_20` | `34` |
| `INNER_21` | `35` |
| `INNER_22` | `36` |
| `INNER_23` | `37` |
| `INNER_24` | `38` |
| `INNER_25` | `39` |
| `INNER_26` | `40` |
| `INNER_27` | `41` |
| `INNER_28` | `42` |
| `INNER_29` | `43` |
| `INNER_30` | `44` |
| `CUSTOM_1` | `71` |
| `CUSTOM_2` | `72` |
| `CUSTOM_3` | `73` |
| `CUSTOM_4` | `74` |
| `CUSTOM_5` | `75` |
| `CUSTOM_6` | `76` |
| `CUSTOM_7` | `77` |
| `CUSTOM_8` | `78` |
| `CUSTOM_9` | `79` |
| `CUSTOM_10` | `80` |
| `CUSTOM_11` | `81` |
| `CUSTOM_12` | `82` |
| `CUSTOM_13` | `83` |
| `CUSTOM_14` | `84` |
| `CUSTOM_15` | `85` |
| `CUSTOM_16` | `86` |
| `CUSTOM_17` | `87` |
| `CUSTOM_18` | `88` |
| `CUSTOM_19` | `89` |
| `CUSTOM_20` | `90` |
| `CUSTOM_21` | `91` |
| `CUSTOM_22` | `92` |
| `CUSTOM_23` | `93` |
| `CUSTOM_24` | `94` |
| `CUSTOM_25` | `95` |
| `CUSTOM_26` | `96` |
| `CUSTOM_27` | `97` |
| `CUSTOM_28` | `98` |
| `CUSTOM_29` | `99` |
| `CUSTOM_30` | `100` |
| `SUBSTRATE_1` | `101` |
| `HOLE` | `47` |
| `COMPONENT_SHAPE` | `48` |
| `COMPONENT_MARKING` | `49` |
| `PIN_SOLDERING` | `50` |
| `PIN_FLOATING` | `51` |
| `COMPONENT_MODEL` | `52` |
| `SHELL_3D_OUTLINE` | `53` |
| `SHELL_3D_TOP` | `54` |
| `SHELL_3D_BOTTOM` | `55` |
| `DRILL_DRAWING` | `56` |

### `EPCB_LayerStatus` — 层状态

| 成员 | 值 |
|---|---|
| `NOT_USED` | `0` |
| `SHOW` | `1` |
| `HIDDEN` | `2` |

### `EPCB_LayerType` — 图层类型

| 成员 | 值 |
|---|---|
| `SIGNAL` | `"SIGNAL"` |
| `INTERNAL_ELECTRICAL` | `"PLANE"` |
| `SILKSCREEN` | `"SILKSCREEN"` |
| `SOLDER_MASK` | `"SOLDER_MASK"` |
| `PASTE_MASK` | `"PASTE_MASK"` |
| `ASSEMBLY` | `"ASSEMBLY"` |
| `OTHER` | `"OTHER"` |
| `CUSTOM` | `"CUSTOM"` |

### `EPCB_MouseEventType` — 鼠标事件类型

| 成员 | 值 |
|---|---|
| `SELECTED` | `"selected"` |
| `CLEAR_SELECTED` | `"clearSelected"` |
| `MOVE` | `"move"` |

### `EPCB_NetEventType` — 网络事件类型

| 成员 | 值 |
|---|---|
| `ADD` | `"add"` |
| `REMOVE` | `"remove"` |
| `SELECTED` | `"selected"` |

### `EPCB_PcbPlateType` — PCB 板材类型

| 成员 | 值 |
|---|---|
| `NORMAL` | `1` |
| `FPC` | `2` |

### `EPCB_PdfOutputMethod` — PDF 输出方式

| 成员 | 值 |
|---|---|
| `MULTI_PAGE_PDF` | `"A Multi Page PDF"` |
| `MULTIPLE_SINGLE_PAGE_PDF` | `"Multiple Single Page PDF"` |
| `SINGLE_PAGE_PDF` | `"A Single Page PDF"` |

### `EPCB_PrimitiveArcInteractiveMode` — 圆弧交互模式

| 成员 | 值 |
|---|---|
| `TWO_POINT_ARC` | `1` |
| `CENTER_ARC` | `2` |

### `EPCB_PrimitiveDimensionType` — 尺寸标注类型

| 成员 | 值 |
|---|---|
| `RADIUS` | `"Radius Dimension"` |
| `LENGTH` | `"Length Dimension"` |
| `ANGLE` | `"Protractor Dimension"` |

### `EPCB_PrimitiveEventType` — 图元事件类型

| 成员 | 值 |
|---|---|
| `DELETE` | `"delete"` |
| `CREATE` | `"add"` |
| `MODIFY` | `"modify"` |

### `EPCB_PrimitiveFillMode` — 填充图元填充模式

| 成员 | 值 |
|---|---|
| `SOLID` | `0` |
| `MESH` | `1` |
| `INNER_ELECTRICAL_LAYER` | `2` |

### `EPCB_PrimitivePadHeatWeldingConnectionMethod` — 焊盘热焊连接方式

| 成员 | 值 |
|---|---|
| `DIVERGENT` | `"Divergent"` |
| `DIRECT_CONNECTED` | `"Direct-connected"` |
| `NON_CONNECTED` | `"Non-connected"` |

### `EPCB_PrimitivePadHoleType` — 焊盘钻孔类型

| 成员 | 值 |
|---|---|
| `ROUND` | `"ROUND"` |
| `RECTANGLE` | `"RECT"` |
| `SLOT` | `"SLOT"` |

### `EPCB_PrimitivePadShapeType` — 焊盘外形种类

| 成员 | 值 |
|---|---|
| `ELLIPSE` | `"ELLIPSE"` |
| `OBLONG` | `"OVAL"` |
| `RECTANGLE` | `"RECT"` |
| `REGULAR_POLYGON` | `"NGON"` |
| `POLYLINE_COMPLEX_POLYGON` | `"POLYGON"` |

### `EPCB_PrimitivePadType` — 焊盘类型

| 成员 | 值 |
|---|---|
| `NORMAL` | `0` |
| `TEST` | `1` |
| `MARK_POINT` | `2` |

### `EPCB_PrimitivePourFillMethod` — 覆铜填充方法

| 成员 | 值 |
|---|---|
| `GRID45` | `"45grid"` |
| `GRID` | `"90grid"` |
| `SOLID` | `"solid"` |

### `EPCB_PrimitiveRegionRuleType` — 区域图元区域规则类型

| 成员 | 值 |
|---|---|
| `NO_COMPONENTS` | `2` |
| `NO_VIAS` | `3` |
| `NO_WIRES` | `5` |
| `NO_FILLS` | `6` |
| `NO_POURS` | `7` |
| `NO_INNER_ELECTRICAL_LAYERS` | `8` |
| `FOLLOW_REGION_RULE` | `9` |

### `EPCB_PrimitiveStringAlignMode` — 文本对齐模式

| 成员 | 值 |
|---|---|
| `LEFT_TOP` | `1` |
| `LEFT_MIDDLE` | `2` |
| `LEFT_BOTTOM` | `3` |
| `CENTER_TOP` | `4` |
| `CENTER` | `5` |
| `CENTER_BOTTOM` | `6` |
| `RIGHT_TOP` | `7` |
| `RIGHT_MIDDLE` | `8` |
| `RIGHT_BOTTOM` | `9` |

### `EPCB_PrimitiveType` — 图元类型

| 成员 | 值 |
|---|---|
| `ARC` | `"Arc"` |
| `COMPONENT` | `"Component"` |
| `PAD` | `"Pad"` |
| `COMPONENT_PAD` | `"ComponentPad"` |
| `POLYLINE` | `"Polyline"` |
| `POUR` | `"Pour"` |
| `FILL` | `"Fill"` |
| `REGION` | `"Region"` |
| `LINE` | `"Line"` |
| `VIA` | `"Via"` |
| `DIMENSION` | `"Dimension"` |
| `IMAGE` | `"Image"` |
| `OBJECT` | `"Object"` |
| `POURED` | `"Poured"` |
| `STRING` | `"String"` |
| `ATTRIBUTE` | `"Attribute"` |

### `EPCB_PrimitiveViaType` — 过孔类型

| 成员 | 值 |
|---|---|
| `VIA` | `0` |
| `BLIND` | `1` |
| `SUTURE` | `2` |

### `ESCH_DynamicSimulationEnginePullEventType` — 动态仿真引擎拉取事件类型

| 成员 | 值 |
|---|---|
| `SESSION_START` | `"SESSION_START"` |
| `SESSION_PAUSE` | `"SESSION_PAUSE"` |
| `SESSION_RESUME` | `"SESSION_RESUME"` |
| `SESSION_STOP` | `"SESSION_STOP"` |
| `SESSION_STATE_QUERY` | `"SESSION_STATE_QUERY"` |
| `SPEED_SET` | `"SPEED_SET"` |
| `COMPONENT_UPDATE` | `"COMPONENT_UPDATE"` |

### `ESCH_DynamicSimulationEnginePushEventType` — 动态仿真引擎推送事件类型

| 成员 | 值 |
|---|---|
| `SESSION_STATE` | `"SESSION_STATE"` |
| `STREAM_DATA` | `"STREAM_DATA"` |
| `STREAM_SNAPSHOT` | `"STREAM_SNAPSHOT"` |
| `ENGINE_LOG` | `"ENGINE_LOG"` |
| `ENGINE_ERROR` | `"ENGINE_ERROR"` |

### `ESCH_ExportDocumentFileType` — 导出文档文件类型

| 成员 | 值 |
|---|---|
| `PDF` | `"PDF"` |
| `PNG` | `"PNG"` |
| `SVG` | `"SVG"` |

### `ESCH_MouseEventType` — 鼠标事件类型

| 成员 | 值 |
|---|---|
| `SELECTED` | `"selected"` |
| `CLEAR_SELECTED` | `"clearSelected"` |

### `ESCH_PrimitiveComponentType` — 器件类型

| 成员 | 值 |
|---|---|
| `COMPONENT` | `"part"` |
| `DRAWING` | `"sheet"` |
| `NET_FLAG` | `"netflag"` |
| `NET_PORT` | `"netport"` |
| `NON_ELECTRICAL_FLAG` | `"nonElectrical_symbol"` |
| `SHORT_CIRCUIT_FLAG` | `"short_symbol"` |
| `NET_LABEL` | `"netlabel"` |
| `OFF_PAGE_CONNECTOR` | `"offPageConnector"` |
| `DIFFERENTIAL_PAIRS_FLAG` | `"diffPairsFlag"` |
| `CBB_SYMBOL` | `"block_symbol"` |

### `ESCH_PrimitiveEventType` — 图元事件类型

| 成员 | 值 |
|---|---|
| `DELETE` | `"delete"` |
| `CREATE` | `"create"` |
| `MOVE` | `"move"` |
| `CHANGE` | `"change"` |

### `ESCH_PrimitiveFillStyle` — 填充样式

| 成员 | 值 |
|---|---|
| `NONE` | `"None"` |
| `SOLID` | `"Solid"` |
| `GRID` | `"Grid"` |
| `HORIZONTAL_LINE` | `"Horizontal Line"` |
| `VERTICAL_LINE` | `"Vertical Line"` |
| `RHOMBIC_GRID` | `"Rhombic Grid"` |
| `LEFT_SLASH_LINE` | `"Left Slash Line"` |
| `RIGHT_SLASH_LINE` | `"Right Slash Line"` |

### `ESCH_PrimitiveLineType` — 线型

| 成员 | 值 |
|---|---|
| `SOLID` | `0` |
| `DASHED` | `1` |
| `DOTTED` | `2` |
| `DOT_DASHED` | `3` |

### `ESCH_PrimitivePinShape` — 引脚形状

| 成员 | 值 |
|---|---|
| `NONE` | `"None"` |
| `INVERTED` | `"Inverted"` |
| `CLOCK` | `"Clock"` |
| `INVERTED_CLOCK` | `"Inverted Clock"` |

### `ESCH_PrimitivePinType` — 引脚类型

| 成员 | 值 |
|---|---|
| `IN` | `"IN"` |
| `OUT` | `"OUT"` |
| `BI` | `"BI"` |
| `PASSIVE` | `"Passive"` |
| `OPEN_COLLECTOR` | `"Open Collector"` |
| `OPEN_EMITTER` | `"Open Emitter"` |
| `POWER` | `"Power"` |
| `GROUND` | `"Ground"` |
| `HIZ` | `"HIZ"` |
| `TERMINATOR` | `"Terminator"` |
| `UNDEFINED` | `"Undefined"` |

### `ESCH_PrimitiveTextAlignMode` — 文本对齐模式

| 成员 | 值 |
|---|---|
| `LEFT_TOP` | `1` |
| `LEFT_MIDDLE` | `2` |
| `LEFT_BOTTOM` | `3` |
| `CENTER_TOP` | `4` |
| `CENTER` | `5` |
| `CENTER_BOTTOM` | `6` |
| `RIGHT_TOP` | `7` |
| `RIGHT_MIDDLE` | `8` |
| `RIGHT_BOTTOM` | `9` |

### `ESCH_PrimitiveType` — 图元类型

| 成员 | 值 |
|---|---|
| `ARC` | `"Arc"` |
| `BUS` | `"Bus"` |
| `CIRCLE` | `"Circle"` |
| `COMPONENT` | `"Component"` |
| `COMPONENT_PIN` | `"ComponentPin"` |
| `PIN` | `"Pin"` |
| `POLYGON` | `"Polygon"` |
| `RECTANGLE` | `"Rectangle"` |
| `TEXT` | `"Text"` |
| `WIRE` | `"Wire"` |
| `OBJECT` | `"Object"` |
| `BEZIER` | `"Bezier"` |
| `ELLIPSE` | `"Ellipse"` |
| `ATTRIBUTE` | `"Attribute"` |

### `ESCH_ShapeType` — 图元类型

| 成员 | 值 |
|---|---|
| `OBJ` | `"obj"` |
| `POLYLINE` | `"polyline"` |
| `CIRCLE` | `"circle"` |
| `ELLIPSE` | `"ellipse"` |
| `RECT` | `"rect"` |
| `ARC` | `"arc"` |
| `TEXT` | `"text",//` |
| `TABLE` | `"table"` |
| `PIN` | `"pin"` |
| `BUSENTRY` | `"busEntry"` |
| `NOCONNECT` | `"noconnect"` |
| `BUS` | `"bus"` |
| `WIRE` | `"wire"` |
| `BEZIER` | `"bezier"` |
| `ANNOTATION` | `"annotation"` |
| `MASKREGION` | `"maskregion"` |

### `ESCH_SimulationNetlistType` — 仿真网表类型

| 成员 | 值 |
|---|---|
| `NGSPICE` | `"NGspice"` |

### `ESCH_SpiceSimulationEnginePullEventType` — Spice 仿真引擎拉取事件类型

| 成员 | 值 |
|---|---|
| `SIMULATE_NETLIST` | `"SIMULATE_NETLIST"` |
| `VALIDATE_NETLIST` | `"VALIDATE_NETLIST"` |

### `ESCH_SpiceSimulationEnginePushEventType` — Spice 仿真引擎推送事件类型

| 成员 | 值 |
|---|---|
| `SIMULATION_RESULT` | `"SIMULATION_RESULT"` |
| `VALIDATION_RESULT` | `"VALIDATION_RESULT"` |
| `LOG_RESULT` | `"LOG_RESULT"` |
| `ERROR_RESULT` | `"ERROR_RESULT"` |

### `ESYS_BottomPanelTab` — 底部面板标签页

| 成员 | 值 |
|---|---|
| `LIBRARY` | `"library"` |
| `LOG` | `"log"` |
| `PCB_DRC` | `"drcResult"` |
| `SCHEMATIC_DRC` | `"schDrcResult"` |
| `FIND` | `"findResult"` |

### `ESYS_HeaderMenuEnvironment` — 顶部菜单环境

| 成员 | 值 |
|---|---|
| `HOME` | `"home"` |
| `BLANK` | `"blank"` |
| `SCHEMATIC` | `"sch"` |
| `SYMBOL` | `"symbol"` |
| `PCB` | `"pcb"` |
| `FOOTPRINT` | `"footprint"` |
| `PCB_VIEW` | `"pcbView"` |
| `PANEL` | `"panel"` |
| `PANEL_LIBRARY` | `"panelLibrary"` |
| `PANEL_VIEW` | `"panelView"` |
| `SIMULATION_SCHEMATIC_NGSPICE` | `"simulationSchematicNGspice"` |
| `SIMULATION_SCHEMATIC_SIMULIDE` | `"simulationSchematicSimulIDE"` |

### `ESYS_ImportProjectBoardOutlineSource` — 导入工程板边框来源

| 成员 | 值 |
|---|---|
| `FROM_KEEPOUT_LAYER` | `"keepout"` |
| `FROM_MECHANICAL_LAYER_1` | `"mechanical"` |

### `ESYS_ImportProjectImportOption` — 导入工程导入选项

| 成员 | 值 |
|---|---|
| `IMPORT_DOCUMENT` | `"ImportDocument"` |
| `EXTRACT_LIBRARIES` | `"ExtractLibraries"` |
| `IMPORT_DOCUMENT_EXTRACT_LIBRARIES` | `"ImportDocumentExtractLibraries"` |

### `ESYS_ImportProjectSchematicObjectStyle` — 导入工程原理图图元样式

| 成员 | 值 |
|---|---|
| `USE_SYSTEM_THEME` | `"system"` |
| `USE_SOURCE_FILE_STYLE` | `"custom"` |

### `ESYS_ImportProjectViaSolderMaskExpansion` — 导入工程过孔阻焊扩展

| 成员 | 值 |
|---|---|
| `ALL_COVER_OIL` | `"cover"` |
| `FOLLOW_ORIGINAL_SETTING` | `"custom"` |

### `ESYS_LeftPanelTab` — 左侧面板标签页

| 成员 | 值 |
|---|---|
| `PROJECT_LIST` | `"project_list"` |
| `PROJECT_DESIGN` | `"projectDesign"` |
| `LIB_DESIGN` | `"libDesign"` |
| `BASIC_LIBRARY` | `"basicLibrary"` |
| `DEVICE_STANDARDIZATION` | `"device-standardization"` |

### `ESYS_LogType` — 日志类型

| 成员 | 值 |
|---|---|
| `INFO` | `"info"` |
| `WARNING` | `"warn"` |
| `ERROR` | `"error"` |
| `FATAL_ERROR` | `"fatalError"` |
| `FIND` | `"find"` |
| `REPLACE` | `"replace"` |
| `OPEN_PROJECT` | `"openProject"` |

### `ESYS_NetlistType` — 网表类型

| 成员 | 值 |
|---|---|
| `ALLEGRO` | `"Allegro"` |
| `PADS` | `"PADS"` |
| `PROTEL2` | `"Protel2"` |
| `JLCEDA_PRO` | `"JLCEDA"` |
| `EASYEDA_PRO` | `"EasyEDA"` |
| `ALTIUM_DESIGNER` | `"Protel2"` |
| `DISA` | `"DISA"` |
| `DISA_SIMULATION` | `"DSNET"` |

### `ESYS_RightPanelTab` — 右侧面板标签页

| 成员 | 值 |
|---|---|
| `SCH_ATTR` | `"sch-attr"` |
| `SCH_FILTER` | `"sch-filter"` |
| `PROJECT_ATTR` | `"project-attr"` |
| `PANEL_LAYER` | `"panel-layer"` |
| `PANEL_ATTR` | `"panel-attr"` |
| `PANEL_FILTER` | `"panel-filter"` |
| `PCB_LAYER` | `"pcb-layer"` |
| `PCB_ATTR` | `"pcb-attr"` |
| `PCB_SKETCHER_ATTR` | `"pcb-sketcher-attr"` |
| `PCB_FILTER` | `"pcb-filter"` |
| `PCB_2D_PREVIEW_ATTR` | `"pcb2d-attr"` |
| `PCB_3D_PREVIEW_LAYER` | `"pcb3d-layer"` |
| `PCB_3D_PREVIEW_ATTR` | `"pcb3d-attr"` |
| `PANEL_3D_PREVIEW_LAYER` | `"panel3d-layer"` |
| `PANEL_3D_PREVIEW_ATTR` | `"panel3d-attr"` |
| `ANNOTATION` | `"annotation"` |

### `ESYS_ShortcutKeyEffectiveEditorDocumentType` — 快捷键生效页面范围

| 成员 | 值 |
|---|---|
| `BLANK` | `0` |
| `HOME` | `1` |
| `SCHEMATIC_PAGE` | `2` |
| `SYMBOL` | `3` |
| `PCB` | `4` |
| `FOOTPRINT` | `5` |
| `PANEL` | `6` |
| `PCB_3D_PREVIEW` | `7` |
| `PCB_2D_PREVIEW` | `8` |
| `PANEL_3D_PREVIEW` | `9` |
| `PANEL_LIBRARY` | `10` |

### `ESYS_ShortcutKeyEffectiveEditorScene` — 快捷键生效场景范围

| 成员 | 值 |
|---|---|
| `EDITOR` | `1` |
| `SELECT_CANVAS` | `2` |
| `NOT_SELECT_CANVAS` | `3` |
| `DRAW` | `4` |
| `PLACE` | `5` |
| `LOCAL` | `6` |

### `ESYS_Theme` — 主题

| 成员 | 值 |
|---|---|
| `LIGHT` | `"light"` |
| `DARK` | `"dark"` |

### `ESYS_ToastMessageType` — 吐司消息类型

| 成员 | 值 |
|---|---|
| `ERROR` | `"error"` |
| `WARNING` | `"warn"` |
| `INFO` | `"info"` |
| `SUCCESS` | `"success"` |
| `ASK` | `"question"` |

### `ESYS_Unit` — 单位

| 成员 | 值 |
|---|---|
| `MILLIMETER` | `"mm"` |
| `CENTIMETER` | `"cm"` |
| `DECIMETER` | `"dm"` |
| `METER` | `"m"` |
| `INCH` | `"inch"` |
| `IN` | `"in"` |
| `MIL` | `"mil"` |

### `ESYS_WindowEventType` — 窗口事件类型

| 成员 | 值 |
|---|---|
| `BLUR` | `"blur"` |
| `FOCUS` | `"focus"` |

### `ESYS_WindowOpenTarget` — 打开窗口上下文目标

| 成员 | 值 |
|---|---|
| `BLANK` | `"_blank"` |
| `SELF` | `"_self"` |

### `ETableDataChangeType` — 表格数据变更类型 */

| 成员 | 值 |
|---|---|
| `NORMAL` | `"NORMAL"` |
| `CHECKED` | `"checked"` |
| `ASC_SORT` | `"ASC_SORT"` |
| `DESC_SORT` | `"DESC_SORT"` |

## 词汇表 · 接口（interface，返回/参数结构）

### `AddRowData`

_（无字段或仅继承）_

### `BoardProps`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `padding` | `number[]` | ? |  |
| `bgColor` | `string` | ? |  |
| `width` | `number` | ? |  |
| `height` | `number` | ? |  |
| `title` | `string` |  |  |
| `children` | `React__default__default.ReactNode` | ? |  |
| `onClick` | `() => void` | ? |  |

### `ButtonProps`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `text` | `string` | ? |  |
| `disabled` | `boolean` | ? |  |
| `type` | `'default' \| 'primary' \| 'danger' \| 'forbidden' \| 'text'` | ? |  |
| `width` | `number \| 'responsive'` | ? |  |
| `icon` | `IconProps` | ? |  |
| `onClick` | `() => void` | ? |  |

### `CellAttributes`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `colSpan` | `number` | ? |  |
| `rowSpan` | `number` | ? |  |
| `style` | `CSSProperties` | ? |  |
| `className` | `string` | ? |  |

### `CellContentReflect`

_（无字段或仅继承）_

### `CheckBoxContentCellParams` extends `HasDisabledCellParams`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `checked` | `boolean` | ? |  |
| `onChange` | `(checked: boolean) => void` |  |  |

### `CheckBoxProps`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `checked` | `boolean` | ? |  |
| `disabled` | `boolean` | ? |  |
| `text` | `string` | ? |  |
| `name` | `string` | ? |  |
| `onlyChangeByBox` | `boolean` | ? |  |
| `onChange` | `(checked: boolean) => void` | ? |  |

### `CheckedOptionalParams`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `isTriggerByRowsUpdate` | `boolean` |  |  |
| `isTriggerByCheckListUpdate` | `boolean` | ? |  |
| `row` | `TableRow` | ? |  |

### `ContainerStyleProps`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `backgroundColor` | `string` | ? |  |
| `borderWidth` | `number` | ? |  |
| `borderColor` | `string` | ? |  |
| `hide` | `boolean` | ? |  |
| `color` | `string` | ? |  |
| `padding` | `number[]` | ? |  |
| `margin` | `number[]` | ? |  |
| `width` | `number \| '100%'` | ? |  |
| `height` | `number \| '100%'` | ? |  |
| `rotate` | `number` | ? |  |
| `cursor` | `'pointer' \| 'default' \| 'none' \| 'move' \| 'text'` | ? |  |
| `invisible` | `boolean` | ? |  |
| `display` | `string` | ? |  |

### `CustomContentCellParams` extends `HasSubTypeCellParams`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `element` | `ReactElement \| {` |  |  |
| `Element` | `(props: K) => ReactElement` |  |  |
| `elementProps` | `K` |  |  |
| `maskStyle` | `CSSProperties` | ? |  |
| `canEdit` | `(instance: any) => boolean` | ? |  |
| `canPaste` | `(instance: any) => boolean` | ? |  |
| `isDisabled` | `(instance: any) => boolean` | ? |  |
| `getValue` | `(instance: any) => T` | ? |  |
| `getText` | `(instance: any) => string` | ? |  |
| `setValue` | `(instance: any, value: T) => void` | ? |  |
| `onEdit` | `(instance: any, value?: T) => void` | ? |  |
| `onConfirm` | `(cell: any) => void` | ? |  |
| `data` | `{` | ? |  |

### `DelRowInfo`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `indexValue` | `string` |  |  |
| `refreshCount` | `number` |  |  |

### `DialogProps`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `title` | `string` |  |  |
| `width` | `number` | ? |  |
| `height` | `number` | ? |  |
| `left` | `number` | ? |  |
| `top` | `number` | ? |  |
| `hide` | `boolean` | ? |  |
| `overlay` | `boolean` | ? |  |
| `maxDragY` | `number` | ? |  |
| `modal` | `boolean` | ? |  |
| `resizeX` | `boolean` | ? |  |
| `resizeY` | `boolean` | ? |  |
| `buttons` | `ButtonProps[]` | ? |  |
| `onClose` | `() => void` | ? |  |
| `children` | `React__default__default.ReactNode` | ? |  |
| `footer` | `React__default__default.ReactNode` | ? |  |

### `DragConfigParams`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `upperLimitIndex` | `number` |  |  |
| `lowerLimitIndex` | `number` |  |  |

### `FlexItemProps` extends `ContainerStyleProps`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `flexRatio` | `number` | ? |  |
| `children` | `React__default__default.ReactNode` | ? |  |
| `onClick` | `() => void` | ? |  |

### `FlexProps` extends `ContainerStyleProps`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `direction` | `'column' \| 'column-reverse' \| 'row' \| 'row-reverse'` | ? |  |
| `alignX` | `'start' \| 'center' \| 'end'` | ? |  |
| `alignY` | `'start' \| 'center' \| 'end' \| 'stretch'` | ? |  |
| `gap` | `number` | ? |  |
| `classes` | `string[]` | ? |  |
| `children` | `React__default__default.ReactNode` | ? |  |
| `onClick` | `() => void` | ? |  |

### `GridItemProps` extends `ContainerStyleProps`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `colSpan` | `number` | ? |  |
| `rowSpan` | `number` | ? |  |
| `align` | `'start' \| 'center' \| 'end' \| 'stretch'` | ? |  |
| `children` | `React__default__default.ReactNode` | ? |  |

### `GridProps` extends `ContainerStyleProps`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `columns` | `number` |  |  |
| `rowGap` | `number` | ? |  |
| `colGap` | `number` | ? |  |
| `children` | `React__default__default.ReactNode` | ? |  |

### `HasDisabledCellParams`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `disabled` | `boolean` | ? |  |

### `HasSubTypeCellParams`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `type` | `string` | ? |  |

### `IDMT_BoardItem`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `itemType` | `EDMT_ItemType.BOARD` |  |  |
| `name` | `string` |  |  |
| `schematic` | `IDMT_SchematicItem` |  |  |
| `pcb` | `IDMT_PcbItem` |  |  |
| `parentProjectUuid` | `string` |  |  |

### `IDMT_BriefProjectItem`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `itemType` | `EDMT_ItemType.PROJECT \| EDMT_ItemType.CBB_PROJECT` |  |  |
| `uuid` | `string` |  |  |
| `friendlyName` | `string` |  |  |
| `teamUuid` | `string` |  |  |
| `folderUuid` | `string` | ? |  |

### `IDMT_EditorDocumentItem`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `documentType` | `EDMT_EditorDocumentType` |  |  |
| `uuid` | `string` |  |  |
| `tabId` | `string` |  |  |
| `parentProjectUuid` | `string` | ? |  |
| `parentLibraryUuid` | `string` | ? |  |

### `IDMT_EditorSplitScreenItem`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `id` | `string` |  |  |
| `fatherId` | `string` | ? |  |
| `tabs` | `Array<IDMT_EditorTabItem>` | ? |  |
| `direction` | `EDMT_EditorSplitScreenDirection` | ? |  |
| `children` | `Array<IDMT_EditorSplitScreenItem>` | ? |  |

### `IDMT_EditorTabItem`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `title` | `string` |  |  |
| `tabId` | `string` |  |  |
| `documentType` | `EDMT_EditorDocumentType` |  |  |
| `draggable` | `boolean` |  |  |
| `isAbleDelete` | `boolean` |  |  |
| `notUseI18n` | `boolean` | ? | 标签页是否不使用 I18n 功能（内部功能） |

### `IDMT_FolderItem`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `itemType` | `EDMT_ItemType.FOLDER` |  |  |
| `uuid` | `string` |  |  |
| `name` | `string` |  |  |
| `teamUuid` | `string` |  |  |
| `description` | `string` | ? |  |
| `parentFolderUuid` | `string` |  |  |
| `childrenFoldersUuid` | `Array<string>` | ? |  |

### `IDMT_IndicatorMarkerShape`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `type` | `EDMT_IndicatorMarkerType` |  |  |
| `x` | `number` | ? | 点：坐标 X |
| `y` | `number` | ? | 点：坐标 Y |
| `r` | `number` | ? | 圆形：半径 |
| `startX` | `number` | ? | 线段 \| 圆弧：起始点 X |
| `startY` | `number` | ? | 线段 \| 圆弧：起始点 Y |
| `endX` | `number` | ? | 线段 \| 圆弧：终止点 X |
| `endY` | `number` | ? | 线段 \| 圆弧：终止点 Y |
| `top` | `number` | ? | 矩形：上 Y |
| `bottom` | `number` | ? | 矩形：下 Y |
| `left` | `number` | ? | 矩形：左 X |
| `right` | `number` | ? | 矩形：右 X |
| `angle` | `number` | ? | 圆弧：角度 |

### `IDMT_PanelItem`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `itemType` | `EDMT_ItemType.PANEL` |  |  |
| `uuid` | `string` |  |  |
| `name` | `string` |  |  |
| `parentProjectUuid` | `string` |  |  |

### `IDMT_PcbItem`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `itemType` | `EDMT_ItemType.PCB \| EDMT_ItemType.CBB_PCB` |  |  |
| `uuid` | `string` |  |  |
| `name` | `string` |  |  |
| `parentProjectUuid` | `string` |  |  |
| `parentBoardName` | `string` | ? |  |

### `IDMT_ProjectItem` extends `IDMT_BriefProjectItem`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `name` | `string` |  |  |
| `description` | `string` | ? |  |
| `data` | `Array<IDMT_BoardItem \| IDMT_SchematicItem \| IDMT_PcbItem \| IDMT_PanelItem>` |  |  |
| `collaborationMode` | `EDMT_ProjectCollaborationMode` | ? |  |

### `IDMT_SchematicItem`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `itemType` | `EDMT_ItemType.SCHEMATIC \| EDMT_ItemType.CBB_SCHEMATIC` |  |  |
| `uuid` | `string` |  |  |
| `name` | `string` |  |  |
| `page` | `Array<IDMT_SchematicPageItem>` |  |  |
| `parentProjectUuid` | `string` |  |  |
| `parentBoardName` | `string` | ? |  |
| `cbbSymbol` | `ILIB_SymbolItem` | ? |  |

### `IDMT_SchematicPageItem`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `itemType` | `EDMT_ItemType.SCHEMATIC_PAGE` |  |  |
| `uuid` | `string` |  |  |
| `name` | `string` |  |  |
| `parentSchematicUuid` | `string` |  |  |
| `showTitleBlock` | `boolean` |  |  |
| `titleBlockData` | `{` |  |  |
| `showTitle` | `boolean` |  |  |
| `showValue` | `boolean` |  |  |
| `value` | `any` |  |  |

### `IDMT_TeamItem`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `itemType` | `EDMT_ItemType.TEAM` |  |  |
| `name` | `string` |  |  |
| `uuid` | `string` |  |  |
| `identity` | `number` |  |  |

### `IDMT_WorkspaceItem`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `itemType` | `EDMT_ItemType.WORKSPACE` |  |  |
| `name` | `string` |  |  |
| `uuid` | `string` |  |  |

### `ILIB_3DModelItem`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `libraryType` | `ELIB_LibraryType.MODEL` |  |  |
| `uuid` | `string` |  |  |
| `libraryUuid` | `string` |  |  |
| `name` | `string` |  |  |
| `classification` | `ILIB_ClassificationIndex \| Array<string>` | ? |  |
| `description` | `string` | ? |  |

### `ILIB_3DModelSearchItem`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `uuid` | `string` |  |  |
| `libraryUuid` | `string` |  |  |
| `classification` | `ILIB_ClassificationIndex \| Array<string>` | ? |  |
| `ordinal` | `number` |  |  |
| `name` | `string` |  |  |
| `description` | `string` | ? |  |
| `updateTimestamp` | `number` |  |  |
| `ascription` | `string` |  |  |
| `lastModifiedBy` | `string` |  |  |

### `ILIB_CbbItem`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `libraryType` | `ELIB_LibraryType.CBB` |  |  |
| `uuid` | `string` |  |  |
| `libraryUuid` | `string` |  |  |
| `name` | `string` |  |  |
| `classification` | `ILIB_ClassificationIndex \| Array<string>` | ? |  |
| `description` | `string` | ? |  |
| `boards` | `Array<IDMT_BoardItem>` |  |  |

### `ILIB_CbbSearchItem`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `uuid` | `string` |  |  |
| `libraryUuid` | `string` |  |  |
| `classification` | `ILIB_ClassificationIndex \| Array<string>` | ? |  |
| `ordinal` | `number` |  |  |
| `name` | `string` |  |  |
| `description` | `string` | ? |  |
| `updateTimestamp` | `number` |  |  |
| `ascription` | `string` |  |  |
| `lastModifiedBy` | `string` |  |  |

### `ILIB_ClassificationIndex`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `libraryUuid` | `string` |  |  |
| `libraryType` | `ELIB_LibraryType` |  |  |
| `primaryClassificationUuid` | `string` |  |  |
| `secondaryClassificationUuid` | `string` | ? |  |

### `ILIB_DeviceAssociationItem`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `symbolType` | `ELIB_SymbolType` |  | 符号类型 |
| `symbolUuid` | `string` |  | 符号 UUID |
| `symbol` | `{` |  |  |
| `type` | `ELIB_SymbolType` |  |  |
| `uuid` | `string` |  |  |
| `libraryUuid` | `string` |  |  |
| `footprintUuid` | `string` |  | 封装 UUID |
| `footprint` | `{` | ? |  |
| `uuid` | `string` |  |  |
| `libraryUuid` | `string` |  |  |
| `images` | `Array<string>` | ? |  |

### `ILIB_DeviceExtendPropertyItem`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `name` | `string` | ? |  |
| `designator` | `string` | ? |  |
| `addIntoBom` | `boolean` | ? |  |
| `addIntoPcb` | `boolean` | ? |  |
| `net` | `string` | ? |  |
| `manufacturer` | `string` | ? |  |
| `manufacturerId` | `string` | ? |  |
| `supplier` | `string` | ? |  |
| `supplierId` | `string` | ? |  |
| `otherProperty` | `{` | ? |  |

### `ILIB_DeviceItem`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `libraryType` | `ELIB_LibraryType.DEVICE` |  |  |
| `uuid` | `string` |  |  |
| `libraryUuid` | `string` |  |  |
| `name` | `string` |  |  |
| `classification` | `ILIB_ClassificationIndex \| Array<string>` | ? |  |
| `association` | `ILIB_DeviceAssociationItem` |  |  |
| `description` | `string` | ? |  |
| `property` | `ILIB_DeviceExtendPropertyItem` |  |  |
| `subPartNames` | `[]` |  |  |

### `ILIB_DevicePropertiesForSearch`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `name` | `string` | ? |  |
| `value` | `string` | ? |  |
| `symbolName` | `string` | ? |  |
| `footprintName` | `string` | ? |  |
| `supplierFootprint` | `string` | ? |  |
| `supplierId` | `string` | ? |  |
| `partNumber` | `string` | ? |  |
| `partCode` | `string` | ? |  |

### `ILIB_DeviceSearchItem`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `uuid` | `string` |  |  |
| `libraryUuid` | `string` |  |  |
| `classification` | `ILIB_ClassificationIndex \| Array<string>` | ? |  |
| `ordinal` | `number` |  |  |
| `name` | `string` |  |  |
| `symbolName` | `string` |  | 关联符号名称 |
| `symbolUuid` | `string` |  | 关联符号 UUID |
| `symbol` | `{` |  |  |
| `name` | `string` |  |  |
| `uuid` | `string` |  |  |
| `libraryUuid` | `string` |  |  |
| `footprintName` | `string` | ? | 关联封装名称 |
| `footprintUuid` | `string` |  | 关联封装 UUID |
| `footprint` | `{` | ? |  |
| `name` | `string` |  |  |
| `uuid` | `string` |  |  |
| `libraryUuid` | `string` |  |  |
| `model3DName` | `string` | ? | 关联 3D 模型名称 |
| `model3DUuid` | `string` |  | 关联 3D 模型 UUID |
| `model3D` | `{` | ? |  |
| `name` | `string` |  |  |
| `uuid` | `string` |  |  |
| `libraryUuid` | `string` |  |  |
| `imageUuid` | `string` | ? |  |
| `description` | `string` | ? |  |
| `manufacturer` | `string` | ? | 制造商 |
| `manufacturerId` | `string` | ? | 制造商编号 |
| `supplier` | `string` | ? | 供应商 |
| `supplierId` | `string` | ? | 供应商编号 |
| `lcscInventory` | `number` | ? | 立创商城库存 |
| `lcscPrice` | `number` | ? | 立创商城价格 |
| `jlcInventory` | `number` | ? | 嘉立创库存 |
| `jlcPrice` | `number` | ? | 嘉立创价格 |
| `jlcLibraryCategory` | `ELIB_DeviceJlcLibraryCategory` | ? | 嘉立创库类别 |
| `otherProperty` | `{` | ? |  |

### `ILIB_ExtendLibrary3DModelFunctions` extends `ILIB_ExtendLibraryFunctions`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `getList` | `(props: ILIB_ExtendLibrarySearchProperty<{}>) => Promise<ILIB_ExtendLibrarySearchResult<ILIB_ExtendLibraryItemIndex & ILIB_ExtendLibrarySearchResultDataLine & {` |  |  |
| `modelType` | `'step'` |  |  |

### `ILIB_ExtendLibraryCbbFunctions` extends `ILIB_ExtendLibraryFunctions`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `getList` | `(props: any) => Promise<ILIB_ExtendLibrarySearchResult<ILIB_ExtendLibraryItem & ILIB_ExtendLibrarySearchResultDataLine & {` |  |  |
| `schematics` | `Array<{` | ? |  |
| `uuid` | `string` |  |  |
| `name` | `string` |  |  |
| `updateTime` | `string` |  |  |
| `description` | `string` | ? |  |
| `pcbs` | `Array<{` | ? |  |
| `uuid` | `string` |  |  |
| `name` | `string` |  |  |
| `updateTime` | `number` |  |  |
| `thumb` | `string` | ? |  |
| `createTime` | `number` | ? |  |
| `creator` | `ILIB_ExtendLibraryUserIndex` | ? |  |
| `modifier` | `ILIB_ExtendLibraryUserIndex` | ? |  |
| `description` | `string` | ? |  |
| `boards` | `Array<{` | ? |  |
| `pcbUuid` | `string` |  |  |
| `schUuid` | `string` |  |  |
| `name` | `string` |  |  |
| `sheets` | `Array<{` | ? |  |
| `uuid` | `string` |  |  |
| `name` | `string` |  |  |
| `belongSchematicUuid` | `string` |  |  |
| `updateTime` | `number` |  |  |
| `thumb` | `string` | ? |  |
| `createTime` | `number` | ? |  |
| `creator` | `ILIB_ExtendLibraryUserIndex` | ? |  |
| `modifier` | `ILIB_ExtendLibraryUserIndex` | ? |  |
| `description` | `string` | ? |  |

### `ILIB_ExtendLibraryClassificationIndex`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `primaryClassificationName` | `string` | ? |  |
| `primaryClassificationUuid` | `string` | ? |  |
| `secondaryClassificationName` | `string` | ? |  |
| `secondaryClassificationUuid` | `string` | ? |  |

### `ILIB_ExtendLibraryDeviceFunctions` extends `ILIB_ExtendLibraryFunctions`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `getList` | `(props: ILIB_ExtendLibrarySearchProperty<{` |  |  |
| `attributes` | `{` | ? |  |
| `symbolType` | `ELIB_SymbolType` | ? |  |
| `classification` | `ILIB_ExtendLibraryClassificationIndex \| Array<string>` | ? |  |
| `symbol` | `ILIB_ExtendLibraryItem & {` | ? |  |
| `symbolType` | `ELIB_SymbolType` |  |  |
| `footprint` | `ILIB_ExtendLibraryItem` | ? |  |
| `model3d` | `ILIB_ExtendLibraryItemIndex & {` | ? |  |
| `adjustment` | `{` | ? |  |
| `size` | `{` | ? |  |
| `x` | `number` |  |  |
| `y` | `number` |  |  |
| `z` | `number` |  |  |
| `rotation` | `{` | ? |  |
| `x` | `number` |  |  |
| `y` | `number` |  |  |
| `z` | `number` |  |  |
| `offset` | `{` | ? |  |
| `x` | `number` |  |  |
| `y` | `number` |  |  |
| `z` | `number` |  |  |
| `value` | `string` | ? |  |
| `supplierPart` | `string` | ? |  |
| `manufacturer` | `string` | ? |  |
| `description` | `string` | ? |  |
| `updateTime` | `number` | ? |  |
| `createTime` | `number` | ? |  |
| `attributes` | `{` | ? |  |
| `getSupportedSymbolTypes` | `() => Promise<Array<ELIB_SymbolType>>` |  | 获取支持的符号类型 |
| `getSupportedPreviewTypes` | `() => Promise<Array<ELIB_PreviewType>>` |  | 获取支持的预览类型 |

### `ILIB_ExtendLibraryFootprintFunctions` extends `ILIB_ExtendLibraryFunctions`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `getList` | `(props: ILIB_ExtendLibrarySearchProperty<{}>) => Promise<ILIB_ExtendLibrarySearchResult<ILIB_ExtendLibraryItem & ILIB_ExtendLibrarySearchResultDataLine>>` |  |  |

### `ILIB_ExtendLibraryFunctions`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `getDetail` | `(uuid: string) => Promise<any>` |  | 获取详细信息 |
| `getClassificationTree` | `() => Promise<Array<{` |  | 获取分类树 |
| `name` | `string` |  |  |
| `uuid` | `string` | ? |  |
| `children` | `Array<{` | ? |  |
| `name` | `string` |  |  |
| `uuid` | `string` | ? |  |
| `getList` | `(props: ILIB_ExtendLibrarySearchProperty<any>) => Promise<ILIB_ExtendLibrarySearchResult<any>>` |  | 获取列表 |

### `ILIB_ExtendLibraryItem` extends `ILIB_ExtendLibraryItemIndex`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `url` | `string` | ? |  |
| `data` | `string \| Blob` | ? |  |

### `ILIB_ExtendLibraryItemIndex`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `uuid` | `string` | ? |  |
| `name` | `string` |  |  |

### `ILIB_ExtendLibrarySearchProperty`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `page` | `number` | ? |  |
| `pageSize` | `number` | ? |  |
| `query` | `T & {` |  |  |
| `wd` | `string` | ? |  |
| `listByTitles` | `Array<string>` | ? |  |
| `classification` | `ILIB_ExtendLibraryClassificationIndex \| Array<string>` | ? |  |

### `ILIB_ExtendLibrarySearchResult`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `count` | `number` |  |  |
| `lists` | `Array<T>` |  |  |
| `page` | `number` |  |  |
| `pageSize` | `number` |  |  |
| `totalPage` | `number` |  |  |

### `ILIB_ExtendLibrarySearchResultDataLine`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `classification` | `ILIB_ExtendLibraryClassificationIndex \| Array<string>` | ? |  |
| `description` | `string` | ? |  |
| `version` | `string` | ? |  |
| `updateTime` | `number` | ? |  |
| `createTime` | `number` | ? |  |
| `creator` | `ILIB_ExtendLibraryUserIndex` | ? |  |
| `modifier` | `ILIB_ExtendLibraryUserIndex` | ? |  |
| `owner` | `ILIB_ExtendLibraryUserIndex` | ? |  |

### `ILIB_ExtendLibrarySymbolFunctions` extends `ILIB_ExtendLibraryFunctions`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `getList` | `(props: ILIB_ExtendLibrarySearchProperty<{` |  |  |
| `symbolType` | `ELIB_SymbolType` | ? |  |
| `symbolType` | `ELIB_SymbolType` |  |  |
| `getSupportedSymbolTypes` | `() => Promise<Array<ELIB_SymbolType>>` |  | 获取支持的符号类型 |

### `ILIB_ExtendLibraryUserIndex`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `name` | `string` | ? |  |
| `uuid` | `string` | ? |  |

### `ILIB_FootprintItem`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `libraryType` | `ELIB_LibraryType.FOOTPRINT` |  |  |
| `uuid` | `string` |  |  |
| `libraryUuid` | `string` |  |  |
| `name` | `string` |  |  |
| `classification` | `ILIB_ClassificationIndex \| Array<string>` | ? |  |
| `description` | `string` | ? |  |

### `ILIB_FootprintPropertiesForSearch`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `name` | `string` | ? |  |

### `ILIB_FootprintSearchItem`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `uuid` | `string` |  |  |
| `libraryUuid` | `string` |  |  |
| `classification` | `ILIB_ClassificationIndex \| Array<string>` | ? |  |
| `ordinal` | `number` |  |  |
| `name` | `string` |  |  |
| `description` | `string` | ? |  |
| `updateTimestamp` | `number` |  |  |
| `ascription` | `string` |  |  |
| `lastModifiedBy` | `string` |  |  |

### `ILIB_LibraryInfo`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `name` | `string` |  |  |
| `uuid` | `string` |  |  |

### `ILIB_LibraryItem`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `uuid` | `string` |  |  |
| `libraryType` | `ELIB_LibraryType` |  |  |
| `libraryUuid` | `string` | ? |  |

### `ILIB_PanelLibraryItem`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `libraryType` | `ELIB_LibraryType.PANEL_LIBRARY` |  |  |
| `uuid` | `string` |  |  |
| `libraryUuid` | `string` |  |  |
| `name` | `string` |  |  |
| `classification` | `ILIB_ClassificationIndex \| Array<string>` | ? |  |
| `description` | `string` | ? |  |

### `ILIB_PanelLibrarySearchItem`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `uuid` | `string` |  |  |
| `libraryUuid` | `string` |  |  |
| `classification` | `ILIB_ClassificationIndex \| Array<string>` | ? |  |
| `ordinal` | `number` |  |  |
| `name` | `string` |  |  |
| `description` | `string` | ? |  |
| `updateTimestamp` | `number` |  |  |
| `ascription` | `string` |  |  |
| `lastModifiedBy` | `string` |  |  |

### `ILIB_SymbolItem`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `libraryType` | `ELIB_LibraryType.SYMBOL` |  |  |
| `uuid` | `string` |  |  |
| `libraryUuid` | `string` |  |  |
| `cbbUuid` | `string` | ? |  |
| `name` | `string` |  |  |
| `classification` | `ILIB_ClassificationIndex \| Array<string>` | ? |  |
| `type` | `ELIB_SymbolType` |  |  |
| `description` | `string` | ? |  |
| `subPartNames` | `[]` |  |  |

### `ILIB_SymbolPropertiesForSearch`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `name` | `string` | ? |  |

### `ILIB_SymbolSearchItem`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `uuid` | `string` |  |  |
| `libraryUuid` | `string` |  |  |
| `classification` | `ILIB_ClassificationIndex \| Array<string>` | ? |  |
| `ordinal` | `number` |  |  |
| `name` | `string` |  |  |
| `type` | `ELIB_SymbolType` |  |  |
| `description` | `string` | ? |  |
| `updateTimestamp` | `number` |  |  |
| `ascription` | `string` |  |  |
| `lastModifiedBy` | `string` |  |  |

### `IPCB_BomPropertiesTableColumns`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `property` | `string` |  |  |
| `title` | `string` | ? |  |
| `sort` | `null \| 'asc' \| 'desc'` | ? |  |
| `group` | `null \| 'Yes' \| 'No'` | ? |  |
| `orderWeight` | `number` | ? |  |

### `IPCB_DifferentialPairItem`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `name` | `string` |  |  |
| `positiveNet` | `string` |  |  |
| `negativeNet` | `string` |  |  |

### `IPCB_DiscretizeOptions`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `step` | `number` | ? | 离散步长，即相邻离散点之间的最大距离 |

### `IPCB_DiscretizedPoint`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `x` | `number` |  |  |
| `y` | `number` |  |  |

### `IPCB_EqualLengthNetGroupItem`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `name` | `string` |  |  |
| `nets` | `Array<string>` |  |  |
| `color` | `{` |  |  |
| `r` | `number` |  |  |
| `g` | `number` |  |  |
| `b` | `number` |  |  |
| `alpha` | `number` |  |  |

### `IPCB_LayerItem`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `id` | `EPCB_LayerId` |  |  |
| `name` | `string` |  |  |
| `type` | `EPCB_LayerType` |  |  |
| `color` | `string` |  |  |
| `transparency` | `number` |  |  |
| `inactiveColor` | `string` |  |  |
| `inactiveTransparency` | `number` |  |  |
| `layerStatus` | `EPCB_LayerStatus` |  |  |
| `locked` | `boolean` |  |  |

### `IPCB_NetClassItem`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `name` | `string` |  |  |
| `nets` | `Array<string>` |  |  |
| `color` | `{` |  |  |
| `r` | `number` |  |  |
| `g` | `number` |  |  |
| `b` | `number` |  |  |
| `alpha` | `number` |  |  |

### `IPCB_NetInfo`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `net` | `string` |  |  |
| `color` | `{` |  |  |
| `r` | `number` |  |  |
| `g` | `number` |  |  |
| `b` | `number` |  |  |
| `alpha` | `number` |  |  |
| `length` | `number` |  |  |

### `IPCB_PadPairGroupItem`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `name` | `string` |  |  |
| `padPairs` | `Array<[string, string]>` |  |  |

### `IPCB_PadPairMinWireLengthItem`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `padPair` | `[string, string]` |  |  |
| `minWireLength` | `number` |  |  |

### `IPCB_Primitive`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `getState_PrimitiveType` | `() => EPCB_PrimitiveType` |  |  |
| `getState_PrimitiveId` | `() => string` |  |  |
| `create` | `() => IPCB_Primitive \| Promise<IPCB_Primitive>` |  |  |
| `toAsync` | `() => IPCB_Primitive` |  |  |
| `toSync` | `() => IPCB_Primitive` |  |  |
| `isAsync` | `() => boolean` |  |  |
| `reset` | `() => IPCB_Primitive \| Promise<IPCB_Primitive>` |  |  |
| `done` | `() => IPCB_Primitive \| Promise<IPCB_Primitive>` |  |  |

### `IPCB_PrimitiveAPI`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `create` | `(...args: any[]) => IPCB_Primitive \| undefined \| Promise<IPCB_Primitive> \| Promise<IPCB_Primitive \| undefined>` |  |  |
| `delete` | `(primitiveIds: string \| any \| Array<string> \| Array<any>) => boolean \| Promise<boolean>` |  |  |
| `modify` | `(primitiveId: string \| any, ...args: any[]) => IPCB_Primitive \| undefined \| Promise<IPCB_Primitive> \| Promise<IPCB_Primitive \| undefined>` |  |  |
| `get` | `{` |  |  |
| `getAllPrimitiveId` | `(...args: any[]) => Array<string> \| Promise<Array<string>>` |  |  |
| `getAll` | `(...args: any[]) => Array<IPCB_Primitive> \| Promise<Array<IPCB_Primitive>>` |  |  |

### `IPCB_PrimitivePadHeatWelding`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `connectionMethod` | `EPCB_PrimitivePadHeatWeldingConnectionMethod` |  |  |
| `divergenceSpacing` | `number` | ? |  |
| `divergenceLineWidth` | `number` | ? |  |
| `divergenceAngle` | `number` | ? |  |

### `IPCB_PrimitivePouredPourFill`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `path` | `IPCB_ComplexPolygon` |  |  |
| `lineWidth` | `number` |  |  |
| `fill` | `boolean` |  |  |
| `id` | `string` |  |  |

### `IPCB_PrimitiveSolderMaskAndPasteMaskExpansion`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `topSolderMask` | `number` | ? |  |
| `bottomSolderMask` | `number` | ? |  |
| `topPasteMask` | `number` | ? |  |
| `bottomPasteMask` | `number` | ? |  |

### `ISCH_NetInfo`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `net` | `string` |  |  |
| `wires` | `Array<ISCH_WireInfo>` |  |  |

### `ISCH_Primitive`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `getState_PrimitiveType` | `() => ESCH_PrimitiveType` |  |  |
| `getState_PrimitiveId` | `() => string` |  |  |
| `create` | `() => ISCH_Primitive \| Promise<ISCH_Primitive>` |  |  |
| `toAsync` | `() => ISCH_Primitive` |  |  |
| `toSync` | `() => ISCH_Primitive` |  |  |
| `isAsync` | `() => boolean` |  |  |
| `reset` | `() => ISCH_Primitive \| Promise<ISCH_Primitive>` |  |  |
| `done` | `() => ISCH_Primitive \| Promise<ISCH_Primitive>` |  |  |

### `ISCH_PrimitiveAPI`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `create` | `(...args: any[]) => ISCH_Primitive \| undefined \| Promise<ISCH_Primitive> \| Promise<ISCH_Primitive \| undefined>` |  |  |
| `delete` | `(primitiveIds: string \| any \| Array<string> \| Array<any>) => boolean \| Promise<boolean>` |  |  |
| `modify` | `(primitiveId: string \| any, ...args: any[]) => ISCH_Primitive \| undefined \| Promise<ISCH_Primitive> \| Promise<ISCH_Primitive \| undefined>` |  |  |
| `get` | `{` |  |  |
| `getAllPrimitiveId` | `(...args: any[]) => Array<string> \| Promise<Array<string>>` |  |  |
| `getAll` | `(...args: any[]) => Array<ISCH_Primitive> \| Promise<Array<ISCH_Primitive>>` |  |  |

### `ISCH_ProjectNetInfo`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `schematicName` | `string` |  |  |
| `schematicUuid` | `string` |  |  |
| `boardName` | `string` |  |  |
| `nets` | `Array<ISCH_NetInfo>` |  |  |

### `ISCH_WireInfo`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `name` | `string` |  |  |
| `id` | `string` |  |  |
| `globalNetName` | `string` |  |  |
| `pageName` | `string` |  |  |
| `pageUuid` | `string` |  |  |

### `ISYS_FileSystemFileList`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `fileName` | `string` |  |  |
| `isDirectory` | `boolean` |  |  |
| `subFiles` | `Array<ISYS_FileSystemFileList>` | ? |  |
| `relativePath` | `string` | ? |  |
| `fullPath` | `string` |  |  |

### `ISYS_HeaderMenuSub1MenuItem`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `id` | `string` |  |  |
| `title` | `string` |  |  |
| `icon` | `string` | ? |  |
| `registerFn` | `string` | ? |  |
| `menuItems` | `Array<ISYS_HeaderMenuSub2MenuItem \| null>` | ? |  |

### `ISYS_HeaderMenuSub2MenuItem`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `id` | `string` |  |  |
| `title` | `string` |  |  |
| `icon` | `string` | ? |  |
| `registerFn` | `string` | ? |  |

### `ISYS_HeaderMenuTopMenuItem`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `id` | `string` |  |  |
| `title` | `string` |  |  |
| `registerFn` | `string` | ? |  |
| `menuItems` | `Array<ISYS_HeaderMenuSub1MenuItem \| null>` | ? |  |

### `ISYS_HeaderMenus`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `home` | `Array<ISYS_HeaderMenuTopMenuItem>` | ? |  |
| `blank` | `Array<ISYS_HeaderMenuTopMenuItem>` | ? |  |
| `schematic` | `Array<ISYS_HeaderMenuTopMenuItem>` | ? |  |
| `sch` | `Array<ISYS_HeaderMenuTopMenuItem>` | ? | 原理图 |
| `symbol` | `Array<ISYS_HeaderMenuTopMenuItem>` | ? |  |
| `pcb` | `Array<ISYS_HeaderMenuTopMenuItem>` | ? |  |
| `footprint` | `Array<ISYS_HeaderMenuTopMenuItem>` | ? |  |
| `pcbView` | `Array<ISYS_HeaderMenuTopMenuItem>` | ? |  |
| `panel` | `Array<ISYS_HeaderMenuTopMenuItem>` | ? |  |
| `panelLibrary` | `Array<ISYS_HeaderMenuTopMenuItem>` | ? |  |
| `panelView` | `Array<ISYS_HeaderMenuTopMenuItem>` | ? |  |
| `simulationSchematicNGspice` | `Array<ISYS_HeaderMenuTopMenuItem>` | ? |  |
| `simulationSchematicSimulIDE` | `Array<ISYS_HeaderMenuTopMenuItem>` | ? |  |

### `ISYS_LanguageKeyValuePairs`

_（无字段或仅继承）_

### `ISYS_LogLine`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `timestamp` | `number` |  |  |
| `type` | `ESYS_LogType` |  |  |
| `message` | `string` |  |  |

### `ISYS_MessageBusTask`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `cancel` | `() => void` |  |  |
| `running` | `() => boolean` |  | 检查运行状态 |
| `execute` | `(message: any) => Promise<void>` |  | 任务处理 |

### `ISYS_MultilingualLanguagesData`

_（无字段或仅继承）_

### `ISYS_ReactComponentizationDialogInterface`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `Components` | `LC_DESIGN_COMPONENTS` |  | 预制组件 |
| `LC_DESIGN_COMPONENTS_NAMES` | `typeof LC_DESIGN_COMPONENTS_NAMES` |  | 组件名称常量 |
| `WorkerPortal` | `new () => ISYS_ReactComponentizationDialogWorkerPortal` |  | WorkerPortal 类 |
| `VirtualRender` | `new () => ISYS_ReactComponentizationDialogVirtualRender` |  | VirtualRender 类 |

### `ISYS_ReactComponentizationDialogReactInstance`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `createContext` | `<T>(defaultValue: T) => React.Context<T>` |  | 创建 React Context |
| `useContext` | `<T>(context: React.Context<T>) => T` |  | 读取和订阅 Context 的值 |
| `useRef` | `<T>(initialValue: T) => React.MutableRefObject<T>` |  | 创建一个可变的 ref 对象 |
| `useEffect` | `(effect: () => undefined \| (() => undefined), deps?: React.DependencyList) => void` |  | 执行副作用操作 |
| `createElement` | `<P extends Record<string, unknown>>(type: React.ElementType<P>, props?: P \| null, ...children: React.ReactNode[]) => React.ReactElement<P>` |  | 创建并返回指定类型的新 React 元素 |

### `ISYS_ReactComponentizationDialogReconcilerInstance`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `default` | `any` |  | Reconciler 构造函数 |
| `constants` | `{` |  | Reconciler 常量 |
| `ContinuousEventPriority` | `number` |  | 连续事件优先级 |
| `DiscreteEventPriority` | `number` |  | 离散事件优先级 |
| `DefaultEventPriority` | `number` |  | 默认事件优先级 |
| `ConcurrentRoot` | `number` |  | 并发根节点标签 |

### `ISYS_ReactComponentizationDialogVirtualRender`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `render` | `(element: React.ReactNode) => void` |  | 渲染 React 元素 |

### `ISYS_ReactComponentizationDialogWorkerPortal`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `Provider` | `React.ComponentType<React.PropsWithChildren<unknown>>` |  | Provider 组件 |
| `createComponent` | `(handle: string, type: string, props: Record<string, unknown>, parent: string) => void` |  | 创建组件 |
| `updateComponent` | `(handle: string, props: Record<string, unknown>) => void` |  | 更新组件 |
| `detachComponent` | `(handle: string) => void` |  | 销毁组件 |
| `bindEvent` | `(handle: string, callback: (event: unknown) => void) => void` |  | 绑定事件处理器 |
| `dispatchEvent` | `(handle: string, event: unknown) => void` |  | 触发事件 |

### `ISYS_RightClickMenuItem`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `id` | `string` |  |  |
| `title` | `string` | ? |  |
| `icon` | `string` | ? |  |
| `registerFn` | `string` | ? |  |
| `menuItems` | `Array<ISYS_RightClickMenuItem \| null>` | ? |  |

### `ISYS_WindowEventListenerRemovableObject`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `type` | `ESYS_WindowEventType` |  |  |
| `listener` | `(ev: any) => any` |  |  |
| `options` | `{` | ? |  |
| `capture` | `boolean` | ? |  |

### `ImageProps`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `src` | `string` |  |  |
| `width` | `number` | ? |  |
| `height` | `number` | ? |  |
| `title` | `string` | ? |  |
| `onClick` | `() => void` | ? |  |

### `InputContentCellParams` extends `HasDisabledCellParams`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `value` | `string` | ? |  |
| `onChange` | `(value: string) => void` |  |  |
| `onConfirm` | `(cell: any) => void` |  |  |
| `children` | `ReactElement` | ? |  |

### `InputProps`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `width` | `number` | ? |  |
| `disabled` | `boolean` | ? |  |
| `readonly` | `boolean` | ? |  |
| `clearBtn` | `boolean` | ? |  |
| `clickBtn` | `boolean` | ? |  |
| `dropDownList` | `ListChildren$1[]` | ? |  |
| `searchBtn` | `boolean` | ? |  |
| `value` | `string` | ? |  |
| `placeholder` | `string` | ? |  |
| `preText` | `string` | ? |  |
| `type` | `'text' \| 'telephone' \| 'number' \| 'password' \| 'color' \| 'email'` |  |  |
| `otherAttr` | `{` | ? |  |
| `testVal` | `string` | ? |  |
| `onClick` | `() => void` | ? |  |
| `onSearchClick` | `(data: string) => void` | ? |  |
| `onFilterClick` | `(data: string) => void` | ? |  |
| `onChange` | `(data: string) => void` | ? |  |
| `onAddClick` | `(data: string) => void` | ? |  |
| `onBlur` | `(data: string) => void` | ? |  |

### `ListChildren`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `title` | `string` |  |  |
| `id` | `string` | ? |  |
| `value` | `string` | ? |  |
| `clearBtn` | `boolean` | ? |  |
| `children` | `ListChildren[]` | ? |  |
| `childrenCollapse` | `boolean` | ? |  |
| `selected` | `boolean` | ? |  |
| `icons` | `IconProps[]` | ? |  |

### `ListProps`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `width` | `number` | ? |  |
| `height` | `number` | ? |  |
| `list` | `ListChildren[]` |  |  |
| `itemHeight` | `number` | ? |  |
| `border` | `boolean` | ? |  |
| `expandEnable` | `boolean` | ? |  |
| `onItemClick` | `(id: string, item: ListChildren) => void` | ? |  |
| `onItemDblclick` | `(id: string) => void` | ? |  |
| `onItemContextmenu` | `(id: string) => void` | ? |  |

### `ModalProps`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `top` | `number` |  |  |
| `left` | `number` |  |  |
| `width` | `number` |  |  |
| `height` | `number` |  |  |
| `overlay` | `boolean` | ? |  |
| `maxDragX` | `number` | ? |  |
| `maxDragY` | `number` | ? |  |
| `hide` | `boolean` | ? |  |
| `resizeX` | `boolean` | ? |  |
| `resizeY` | `boolean` | ? |  |
| `children` | `React__default__default.ReactNode` | ? |  |
| `onMoved` | `(top: number, left: number) => void` | ? |  |

### `MoveRowIndex`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `curIndex` | `number` |  |  |
| `newIndex` | `number` |  |  |

### `RadioGroupProps`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `group` | `RadioProps[]` |  |  |
| `selectedValue` | `string` | ? |  |
| `onlyChangeByBox` | `boolean` | ? |  |
| `lineBreak` | `boolean` | ? |  |
| `gap` | `number` | ? |  |
| `onChange` | `(value: string) => void` | ? |  |

### `RadioProps`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `disabled` | `boolean` | ? |  |
| `text` | `string` |  |  |
| `value` | `string` |  |  |
| `width` | `number` | ? |  |

### `RenderParam`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `clickObj` | `TableClickObj` |  |  |
| `rowNumber` | `number` |  |  |
| `colKey` | `string` |  |  |
| `row` | `TableRow` |  |  |
| `cellData` | `any` |  |  |
| `tableData` | `TableRow[]` |  |  |
| `editingRowNumbers` | `number[]` |  |  |
| `selectedRowNumbers` | `number[]` |  |  |
| `setCellStyle` | `(style: CSSProperties) => void` |  |  |
| `setRowStyle` | `(style: CSSProperties) => void` |  |  |
| `setAllCellStyle` | `(style: CSSProperties) => void` |  |  |
| `setRowData` | `(data: {` |  |  |
| `rowIndex` | `number` |  |  |
| `colKey` | `string` |  |  |
| `value` | `string \| number` |  |  |
| `setTableData` | `(data: TableRow[]) => void` |  |  |
| `onToggleExpand` | `(action: 'Expand' \| 'Collapse', rows: Array<TableRow>, opIndex: number) => void` | ? |  |
| `heightLightStr` | `string` | ? |  |

### `SelectContentCellParams` extends `HasDisabledCellParams`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `value` | `string \| number` | ? |  |
| `onChange` | `(value: string \| number \| Array<string \| number>) => void` |  |  |
| `options` | `SelectOption[]` | ? |  |
| `children` | `ReactElement` | ? |  |

### `SelectListItem`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `title` | `string` |  |  |
| `value` | `string` | ? |  |
| `selected` | `boolean` | ? |  |
| `children` | `SelectListItem[]` | ? |  |

### `SelectOption`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `text` | `string` |  |  |
| `value` | `string \| number` |  |  |
| `disabled` | `boolean` | ? |  |

### `SelectProps`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `width` | `number` | ? |  |
| `disabled` | `boolean` | ? |  |
| `readonly` | `boolean` | ? |  |
| `dropDownList` | `SelectListItem[]` | ? |  |
| `value` | `string` | ? |  |
| `onChange` | `(value: string) => void` | ? |  |

### `SortInfo`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `colKey` | `string` |  |  |
| `key` | `string \| string[]` |  |  |
| `status` | `SortStatus` |  |  |

### `TableCellConfig`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `cellType` | `CellType` | ? |  |
| `cellAttributes` | `CellAttributes` | ? |  |
| `contentType` | `T` | ? |  |
| `content` | `CellContentParams<T>` | ? |  |
| `sortable` | `boolean` | ? |  |
| `sortKey` | `string` | ? |  |

### `TableClickObj`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `rowNumber` | `number` |  |  |
| `colKey` | `string` | ? |  |
| `clickCount` | `number` |  |  |
| `isCtrl` | `boolean` | ? |  |
| `isShift` | `boolean` | ? |  |
| `checked` | `boolean` | ? |  |
| `e` | `React.MouseEvent<HTMLTableDataCellElement> \| null` |  |  |

### `TableColumn`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `key` | `string` |  |  |
| `name` | `string` |  |  |
| `width` | `number` | ? |  |
| `sortable` | `boolean` | ? |  |
| `sortKey` | `string \| string[]` | ? |  |
| `editable` | `boolean \| 1 \| 2` | ? |  |
| `filter` | `boolean` | ? |  |
| `align` | `TableCellAlign` | ? |  |
| `selectList` | `SelectOption[]` | ? |  |
| `ellipsis` | `boolean` | ? |  |
| `fixed` | `TableColFixed` | ? |  |
| `fixedWidth` | `boolean` | ? |  |
| `showBodyTitle` | `boolean` | ? |  |
| `style` | `CSSProperties` | ? |  |
| `onClick` | `(colKey: string, ev: React.MouseEvent<HTMLTableHeaderCellElement>) => void` | ? |  |
| `onCell` | `(row: TableRow, index: number, colKey: string) => CellAttributes \| void` | ? |  |
| `onHeadCell` | `(col: TableColumn) => CellAttributes \| void` | ? |  |
| `render` | `(params: RenderParam) => ReactNode` | ? |  |
| `nameRender` | `() => ReactNode` | ? |  |

### `TableInstance`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `checkAll` | `() => void` |  |  |
| `checkedRow` | `({ row, checked }: {` |  |  |
| `row` | `TableRow` |  |  |
| `checked` | `boolean` |  |  |
| `toSelectRow` | `(row: TableRow, option?: {` |  |  |
| `isCtrl` | `boolean` | ? |  |
| `isShift` | `boolean` | ? |  |
| `downMove` | `(rowNumber?: number) => void` |  |  |
| `upMove` | `(rowNumber?: number) => void` |  |  |
| `scrollSelectedRowIntoView` | `() => void` |  |  |
| `scrollRowIntoView` | `(rowIndex: string) => void` |  |  |
| `handleTableScrollByScrollTop` | `(scrollTop: number) => void` |  |  |
| `refresh` | `() => void` |  |  |
| `cancelSortStatus` | `() => void` |  |  |
| `tableBodyDiv` | `HTMLDivElement \| null` |  |  |
| `revertSelect` | `() => void` |  |  |
| `virtualScrollRowIndexIntoView` | `(rowIdx: number) => void` |  |  |

### `TableOnClickParam`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `clickObj` | `TableClickObj` | ? |  |
| `row` | `TableRow` |  |  |
| `tableData` | `TableRow[]` | ? |  |
| `editingRowNumbers` | `number[]` | ? |  |
| `selectedRowNumbers` | `number[]` | ? |  |
| `allSelectedRowIndexValues` | `Set<string \| number>` | ? |  |
| `isCtrl` | `boolean` | ? |  |
| `isShift` | `boolean` | ? |  |
| `from` | `string` | ? |  |
| `setCellStyle` | `(style: CSSProperties) => void` | ? |  |

### `TableProps`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `id` | `string` | ? |  |
| `index` | `string` |  |  |
| `name` | `string` | ? |  |
| `width` | `number` | ? |  |
| `height` | `number` | ? |  |
| `columns` | `TableColumn[]` |  |  |
| `rows` | `TableRow[]` |  |  |
| `head` | `Array<Array<TableCellProps>>` | ? |  |
| `body` | `Array<Array<TableCellProps>>` | ? |  |
| `foot` | `Array<Array<TableCellProps>>` | ? |  |
| `number` | `boolean` | ? |  |
| `border` | `boolean` | ? |  |
| `headerBorder` | `boolean` | ? |  |
| `stockade` | `boolean` | ? |  |
| `checkbox` | `boolean` | ? |  |
| `checkedList` | `TableRow[]` | ? |  |
| `fixedHeader` | `boolean` | ? |  |
| `showHeader` | `boolean` | ? |  |
| `moveRowIndex` | `MoveRowIndex` | ? |  |
| `delRowInfo` | `DelRowInfo` | ? |  |
| `addRowData` | `AddRowData` | ? |  |
| `openVirtualScroll` | `boolean` | ? |  |
| `searchValue` | `string` | ? |  |
| `selectedRowNumbers` | `number[]` | ? |  |
| `editingRowNumbers` | `number[]` | ? |  |
| `openRowSelectedBgColor` | `boolean` | ? |  |
| `showCustomHeadSettingOnHeadContextmenu` | `boolean` | ? |  |
| `isChangeSortStatus` | `boolean` | ? |  |
| `showStatus` | `boolean` | ? |  |
| `statusNode` | `ReactNode` | ? |  |
| `multiSelect` | `boolean` | ? |  |
| `moveAble` | `boolean` | ? |  |
| `isOnlyHighlightText` | `boolean` | ? |  |
| `rowHeight` | `number` | ? |  |
| `headHeight` | `number` | ? |  |
| `headLineHeight` | `number` | ? |  |
| `enableSelectRowByHover` | `boolean` | ? |  |
| `resetTableDataCount` | `number` | ? |  |
| `resetScrollOnDataChange` | `boolean` | ? |  |
| `enableDragSort` | `boolean` | ? |  |
| `showDragIcon` | `boolean` | ? |  |
| `dragConfig` | `DragConfigParams` | ? |  |
| `openMultiDrag` | `boolean` | ? |  |
| `followHeightLight` | `boolean` | ? |  |
| `resize` | `boolean` | ? |  |
| `isCtrlSelect` | `boolean` | ? |  |
| `isShiftSelect` | `boolean` | ? |  |
| `virtualScrollAutoFirst` | `boolean` | ? |  |
| `scrollXBaseBottom` | `number` | ? |  |
| `extraHeight` | `number` | ? |  |
| `headerStyle` | `CSSProperties` | ? |  |
| `enableScrollX` | `boolean` | ? |  |
| `doubleClick` | `boolean` | ? |  |
| `usePointerDrag` | `boolean` | ? |  |
| `highLightRegexpFn` | `(v: any) => RegExp` | ? |  |
| `enableVerticalHeader` | `boolean` | ? |  |
| `verticalHeaderIgnoreKeys` | `string[]` | ? |  |
| `onCheckRow` | `(rows: TableRow[], rowNumbers: number[], optional: CheckedOptionalParams) => void` | ? |  |
| `onAllChecked` | `(data: TableRow[], checked: boolean) => void` | ? |  |
| `onClick` | `(props: TableOnClickParam) => void` | ? |  |
| `onChange` | `(data: TableRow[], row?: TableRow, type?: ETableDataChangeType, optional?: PlainObject) => void` | ? |  |
| `onContextMenu` | `(rows: TableRow, ev: React.MouseEvent<HTMLTableCellElement>) => void` | ? |  |
| `onRowMouseLeave` | `(row: TableRow, rowIndex: number) => void` | ? |  |
| `onRowMouseEnter` | `(row: TableRow, rowIndex: number) => void` | ? |  |
| `onRowMouseMove` | `(row: TableRow, rowIndex: number) => void` | ? |  |
| `onDragMoveEnd` | `(handlerInitialIndex: number \| number[], insertedRealtimeIndex: number, handlerRealtimeIndex: number \| number[]) => void` | ? |  |
| `onTableScroll` | `(tableScrollHeight: number, currentTableHeight: number, scrollTop: number) => void` | ? |  |
| `searchValueCB` | `(a: any) => void` | ? |  |
| `onColSizeChange` | `(col: TableColumn, cols: TableColumn[]) => void` | ? |  |
| `onSort` | `(info: SortInfo) => void` | ? |  |
| `style` | `CSSProperties` | ? |  |
| `tableBodyStyle` | `CSSProperties` | ? |  |

### `TableRow`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `bgColor` | `string` | ? |  |
| `isError` | `boolean` | ? |  |
| `noCheckbox` | `boolean` | ? |  |
| `fixed` | `boolean` | ? |  |
| `disabledRow` | `boolean` | ? |  |
| `disabledCheckbox` | `boolean` | ? |  |
| `propagationClickHandle` | `boolean` | ? |  |

### `TextAreaProps`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `disabled` | `boolean` | ? |  |
| `value` | `string` | ? |  |
| `width` | `number` | ? |  |
| `height` | `number` | ? |  |
| `resizable` | `{` | ? |  |
| `x` | `boolean` | ? |  |
| `y` | `boolean` | ? |  |
| `placeholder` | `string` | ? |  |
| `name` | `string` | ? |  |
| `onChange` | `(value: string) => void` | ? |  |

### `TextContentCellParams`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `value` | `string` | ? |  |
| `content` | `string` | ? |  |

### `TextProps`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `value` | `string` |  |  |
| `fontFamily` | `string` | ? |  |
| `textAlign` | `'left' \| 'center' \| 'right'` | ? |  |
| `fontSize` | `number` | ? |  |
| `color` | `string` | ? |  |

### `TextareaContentCellParams` extends `HasDisabledCellParams`

| 字段 | 类型 | 可选 | 说明 |
|---|---|:--:|---|
| `value` | `string` | ? |  |
| `onChange` | `(value: string) => void` |  |  |
| `children` | `ReactElement` | ? |  |

## 词汇表 · 类型别名（type）

| 别名 | 定义 | 说明 |
|---|---|---|
| `ComponentProps` | `TComponentsIndex[T] extends React.ComponentType<infer P> ? P : never` |  |
| `IconProps` | `{ /** 模板名称 */ iconClass: string` |  |
| `KComponentsIndex` | `keyof TComponentsIndex` |  |
| `LC_DESIGN_COMPONENTS` | `{ [K in KComponentsIndex]: (props: ReactComponentProps<K>) => React.ReactElement` |  |
| `PlainObject` | `{ [key: string]: any` | 普通对象类型 */ |
| `ReactComponentProps` | `ComponentProps<T>` |  |
| `SortStatus` | `'asc' \| 'desc' \| 'unset'` | 排序状态 */ |
| `TComponentsIndex` | `typeof ComponentsIndex` |  |
| `TPCB_LayerTypesOfInnerLayer` | `EPCB_LayerType.SIGNAL \| EPCB_LayerType.INTERNAL_ELECTRICAL` | 内层允许设置的图层类型 |
| `TPCB_LayersInTheSelectable` | `TPCB_LayersOfInner \| TPCB_LayersOfCustom \| EPCB_LayerId.TOP \| EPCB_LayerId.TOP_SILKSCREEN \| EPCB_LayerId.TOP_SOLDER_MASK \| EPCB_LayerId.TOP_PASTE_MASK \| EPCB_LayerId.TOP_ASSEMBLY \| EPCB_LayerId.TOP_STIFFENER \| EPCB_LayerId.BOTTOM \| EPCB_LayerId.BOTTOM_SILKSCREEN \| EPCB_LayerId.BOTTOM_SO…` | 可选中图层 |
| `TPCB_LayersOfComponent` | `EPCB_LayerId.TOP \| EPCB_LayerId.BOTTOM` | 器件所属层 |
| `TPCB_LayersOfCopper` | `TPCB_LayersOfInner \| EPCB_LayerId.TOP \| EPCB_LayerId.BOTTOM` | 铜箔所属层 |
| `TPCB_LayersOfCustom` | `EPCB_LayerId.CUSTOM_1 \| EPCB_LayerId.CUSTOM_2 \| EPCB_LayerId.CUSTOM_3 \| EPCB_LayerId.CUSTOM_4 \| EPCB_LayerId.CUSTOM_5 \| EPCB_LayerId.CUSTOM_6 \| EPCB_LayerId.CUSTOM_7 \| EPCB_LayerId.CUSTOM_8 \| EPCB_LayerId.CUSTOM_9 \| EPCB_LayerId.CUSTOM_10 \| EPCB_LayerId.CUSTOM_11 \| EPCB_LayerId.CUSTOM_…` | 自定义层 |
| `TPCB_LayersOfDimension` | `TPCB_LayersOfCustom \| EPCB_LayerId.TOP_SILKSCREEN \| EPCB_LayerId.BOTTOM_SILKSCREEN \| EPCB_LayerId.DOCUMENT \| EPCB_LayerId.MECHANICAL` | 尺寸标注所属层 |
| `TPCB_LayersOfFill` | `TPCB_LayersOfCopper \| TPCB_LayersOfCustom \| EPCB_LayerId.TOP_SILKSCREEN \| EPCB_LayerId.TOP_SOLDER_MASK \| EPCB_LayerId.TOP_PASTE_MASK \| EPCB_LayerId.TOP_ASSEMBLY \| EPCB_LayerId.BOTTOM_SILKSCREEN \| EPCB_LayerId.BOTTOM_SOLDER_MASK \| EPCB_LayerId.BOTTOM_PASTE_MASK \| EPCB_LayerId.BOTTOM_ASSEM…` | 填充所属层 |
| `TPCB_LayersOfImage` | `TPCB_LayersOfCopper \| TPCB_LayersOfCustom \| EPCB_LayerId.TOP_SILKSCREEN \| EPCB_LayerId.TOP_SOLDER_MASK \| EPCB_LayerId.TOP_ASSEMBLY \| EPCB_LayerId.BOTTOM_SILKSCREEN \| EPCB_LayerId.BOTTOM_SOLDER_MASK \| EPCB_LayerId.BOTTOM_ASSEMBLY \| EPCB_LayerId.DOCUMENT \| EPCB_LayerId.MECHANICAL \| EPCB_L…` | 复杂多边形图（SVG 图像、文本）所属层 |
| `TPCB_LayersOfInner` | `EPCB_LayerId.INNER_1 \| EPCB_LayerId.INNER_2 \| EPCB_LayerId.INNER_3 \| EPCB_LayerId.INNER_4 \| EPCB_LayerId.INNER_5 \| EPCB_LayerId.INNER_6 \| EPCB_LayerId.INNER_7 \| EPCB_LayerId.INNER_8 \| EPCB_LayerId.INNER_9 \| EPCB_LayerId.INNER_10 \| EPCB_LayerId.INNER_11 \| EPCB_LayerId.INNER_12 \| EPCB_L…` | 内层 |
| `TPCB_LayersOfLine` | `TPCB_LayersOfCopper \| TPCB_LayersOfCustom \| EPCB_LayerId.TOP_SILKSCREEN \| EPCB_LayerId.TOP_SOLDER_MASK \| EPCB_LayerId.TOP_PASTE_MASK \| EPCB_LayerId.TOP_ASSEMBLY \| EPCB_LayerId.BOTTOM_SILKSCREEN \| EPCB_LayerId.BOTTOM_SOLDER_MASK \| EPCB_LayerId.BOTTOM_PASTE_MASK \| EPCB_LayerId.BOTTOM_ASSEM…` | 线所属层 |
| `TPCB_LayersOfObject` | `EPCB_LayerId.TOP_SILKSCREEN \| EPCB_LayerId.BOTTOM_SILKSCREEN \| EPCB_LayerId.DOCUMENT` | 二进制内嵌对象所属层 |
| `TPCB_LayersOfPad` | `EPCB_LayerId.TOP \| EPCB_LayerId.BOTTOM \| EPCB_LayerId.MULTI` | 焊盘所属层 |
| `TPCB_LayersOfRegion` | `TPCB_LayersOfCopper \| EPCB_LayerId.MULTI` | 区域所属层 |
| `TPCB_PolygonSourceArray` | `Array<'L' \| 'ARC' \| 'CARC' \| 'C' \| 'R' \| 'CIRCLE' \| number>` | 单多边形源数组 |
| `TPCB_PrimitiveDimensionCoordinateSet` | `[number, number, number, number, number, number] \| [number, number, number, number, number, number, number, number]` | 尺寸标注坐标集 |
| `TPCB_PrimitivePadHole` | `[EPCB_PrimitivePadHoleType.ROUND, number] \| [EPCB_PrimitivePadHoleType.SLOT, number, number]` | 焊盘钻孔 |
| `TPCB_PrimitivePadShape` | `[EPCB_PrimitivePadShapeType.ELLIPSE \| EPCB_PrimitivePadShapeType.OBLONG \| EPCB_PrimitivePadShapeType.REGULAR_POLYGON, number, number] \| [EPCB_PrimitivePadShapeType.RECTANGLE, number, number, number] \| [EPCB_PrimitivePadShapeType.POLYLINE_COMPLEX_POLYGON, TPCB_PolygonSourceArray \| Array<TPCB_…` | 焊盘外形 |
| `TPCB_PrimitiveSpecialPadShape` | `Array<[number, number, TPCB_PrimitivePadShape]>` | 特殊焊盘外形 |
| `TSYS_ShortcutKeys` | `Array<'SHIFT' \| 'LEFT_SHIFT' \| 'RIGHT_SHIFT' \| 'FN' \| 'ALT' \| 'LEFT_ALT' \| 'RIGHT_ALT' \| 'CONTROL' \| 'LEFT_CONTROL' \| 'RIGHT_CONTROL' \| 'COMMAND' \| 'WIN' \| 'OPTION' \| 'SUPER' \| 'TAB' \| 'SPACE' \| 'UP' \| 'DOWN' \| 'LEFT' \| 'RIGHT' \| 'F1' \| 'F2' \| 'F3' \| 'F4' \| 'F5' \| 'F6' \|…` | 快捷键按键 |
| `TableCellAlign` | `'left' \| 'center' \| 'right'` | 表格对齐方式 */ |
| `TableCellProps` | `string \| TableCellConfig` | 单元格属性 */ |
| `TableColFixed` | `'left' \| 'right'` | 列固定位置 */ |

