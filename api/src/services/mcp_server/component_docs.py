"""
Component documentation registry for the get_component_docs MCP tool.

Provides detailed documentation for all available Bifrost app components,
organized by category with props, descriptions, and usage examples.
"""

CATEGORIES = {
    "layout": "Layout & Structure",
    "forms": "Form Controls",
    "display": "Data Display",
    "navigation": "Navigation",
    "feedback": "Feedback & Overlay",
    "data": "Data & Tables",
    "typography": "Typography & Text",
}

COMPONENT_DOCS: dict[str, dict] = {
    # =========================================================================
    # React core
    # =========================================================================
    "React": {
        "category": "layout",
        "description": "React core object. Provides hooks like useState, useEffect, useMemo, useCallback, useRef, useContext. Available globally in app builder -- do NOT import.",
        "props": {},
        "example": "const [count, setCount] = React.useState(0);",
    },
    "Fragment": {
        "category": "layout",
        "description": "React Fragment for grouping elements without adding extra DOM nodes. Can also use <>...</> syntax.",
        "props": {},
        "example": "<Fragment><span>A</span><span>B</span></Fragment>",
    },

    # =========================================================================
    # Routing
    # =========================================================================
    "Outlet": {
        "category": "navigation",
        "description": "Renders the matched child route. Required in _layout.tsx for routing to work. Do NOT use {children} prop pattern.",
        "props": {},
        "example": (
            '<div className="h-full bg-background overflow-hidden">\n'
            "  <Outlet />\n"
            "</div>"
        ),
    },
    "Link": {
        "category": "navigation",
        "description": "Client-side navigation link. Renders an <a> tag that navigates without full page reload.",
        "props": {
            "to": "string - The target path",
            "className": "string",
        },
        "example": '<Link to="/clients">View Clients</Link>',
    },
    "NavLink": {
        "category": "navigation",
        "description": "Like Link but adds active styling when the route matches. Useful for navigation menus.",
        "props": {
            "to": "string - The target path",
            "className": "string | ((props: { isActive }) => string)",
        },
        "example": '<NavLink to="/dashboard" className={({ isActive }) => isActive ? "font-bold" : ""}>Dashboard</NavLink>',
    },
    "Navigate": {
        "category": "navigation",
        "description": "Declarative redirect component. Navigates to the given path when rendered.",
        "props": {
            "to": "string - The target path",
            "replace": "boolean - Replace current history entry",
        },
        "example": '<Navigate to="/login" replace />',
    },

    # =========================================================================
    # Layout - Card
    # =========================================================================
    "Card": {
        "category": "layout",
        "description": "Container with header, content, and footer sections. Renders a rounded bordered div with shadow.",
        "children": ["CardHeader", "CardTitle", "CardAction", "CardDescription", "CardContent", "CardFooter"],
        "props": {
            "className": "string",
        },
        "example": (
            "<Card>\n"
            "  <CardHeader>\n"
            "    <CardTitle>Title</CardTitle>\n"
            "    <CardDescription>Description text</CardDescription>\n"
            "  </CardHeader>\n"
            "  <CardContent>Body content here</CardContent>\n"
            "  <CardFooter>Footer actions</CardFooter>\n"
            "</Card>"
        ),
    },
    "CardHeader": {
        "category": "layout",
        "description": "Header section of a Card. Uses CSS grid layout; automatically places CardAction to the right.",
        "props": {"className": "string"},
        "example": "<CardHeader><CardTitle>Title</CardTitle></CardHeader>",
    },
    "CardTitle": {
        "category": "layout",
        "description": "Title text inside CardHeader. Renders semibold text.",
        "props": {"className": "string"},
        "example": "<CardTitle>My Card Title</CardTitle>",
    },
    "CardAction": {
        "category": "layout",
        "description": "Action area in CardHeader, positioned to the top-right. Useful for buttons or menus.",
        "props": {"className": "string"},
        "example": "<CardAction><Button variant=\"outline\" size=\"sm\">Edit</Button></CardAction>",
    },
    "CardDescription": {
        "category": "layout",
        "description": "Muted description text inside CardHeader.",
        "props": {"className": "string"},
        "example": "<CardDescription>Some helpful description</CardDescription>",
    },
    "CardContent": {
        "category": "layout",
        "description": "Main body area of a Card with horizontal padding.",
        "props": {"className": "string"},
        "example": "<CardContent>Content goes here</CardContent>",
    },
    "CardFooter": {
        "category": "layout",
        "description": "Footer section of a Card. Flex container for action buttons.",
        "props": {"className": "string"},
        "example": "<CardFooter><Button>Save</Button></CardFooter>",
    },

    # =========================================================================
    # Forms
    # =========================================================================
    "Button": {
        "category": "forms",
        "description": "Clickable button with variants and sizes.",
        "props": {
            "variant": "\"default\" | \"destructive\" | \"outline\" | \"secondary\" | \"ghost\" | \"link\"",
            "size": "\"default\" | \"sm\" | \"lg\" | \"icon\" | \"icon-sm\" | \"icon-lg\"",
            "disabled": "boolean",
            "onClick": "() => void",
            "asChild": "boolean - Render as child element (Slot)",
        },
        "example": '<Button variant="outline" onClick={() => alert("hi")}>Click me</Button>',
    },
    "Input": {
        "category": "forms",
        "description": "Text input field. Standard HTML input with styled appearance.",
        "props": {
            "type": "string - e.g. \"text\", \"email\", \"password\", \"number\"",
            "placeholder": "string",
            "value": "string",
            "onChange": "(e: ChangeEvent) => void",
            "disabled": "boolean",
        },
        "example": '<Input type="text" placeholder="Enter name..." value={name} onChange={(e) => setName(e.target.value)} />',
    },
    "Label": {
        "category": "forms",
        "description": "Accessible label for form controls. Pairs with Input, Select, etc.",
        "props": {
            "htmlFor": "string - ID of the associated input",
        },
        "example": '<Label htmlFor="email">Email</Label>',
    },
    "Textarea": {
        "category": "forms",
        "description": "Multi-line text input with auto-sizing.",
        "props": {
            "placeholder": "string",
            "value": "string",
            "onChange": "(e: ChangeEvent) => void",
            "disabled": "boolean",
            "rows": "number",
        },
        "example": '<Textarea placeholder="Enter description..." value={desc} onChange={(e) => setDesc(e.target.value)} />',
    },
    "Checkbox": {
        "category": "forms",
        "description": "Checkable box for boolean values.",
        "props": {
            "checked": "boolean | \"indeterminate\"",
            "onCheckedChange": "(checked: boolean) => void",
            "disabled": "boolean",
        },
        "example": '<div className="flex items-center gap-2"><Checkbox checked={agreed} onCheckedChange={setAgreed} /><Label>I agree</Label></div>',
    },
    "Switch": {
        "category": "forms",
        "description": "Toggle switch for on/off states.",
        "props": {
            "checked": "boolean",
            "onCheckedChange": "(checked: boolean) => void",
            "disabled": "boolean",
        },
        "example": '<div className="flex items-center gap-2"><Switch checked={enabled} onCheckedChange={setEnabled} /><Label>Enable notifications</Label></div>',
    },
    "Select": {
        "category": "forms",
        "description": "Dropdown select menu. Compound component with Trigger, Content, and Items.",
        "children": ["SelectContent", "SelectGroup", "SelectItem", "SelectLabel", "SelectTrigger", "SelectValue", "SelectSeparator"],
        "props": {
            "value": "string",
            "onValueChange": "(value: string) => void",
            "defaultValue": "string",
        },
        "example": (
            '<Select value={status} onValueChange={setStatus}>\n'
            '  <SelectTrigger>\n'
            '    <SelectValue placeholder="Select status..." />\n'
            '  </SelectTrigger>\n'
            '  <SelectContent>\n'
            '    <SelectItem value="active">Active</SelectItem>\n'
            '    <SelectItem value="inactive">Inactive</SelectItem>\n'
            '  </SelectContent>\n'
            '</Select>'
        ),
    },
    "SelectTrigger": {
        "category": "forms",
        "description": "Button that opens the Select dropdown. Renders a chevron icon.",
        "props": {
            "size": "\"sm\" | \"default\"",
            "className": "string",
        },
        "example": '<SelectTrigger><SelectValue placeholder="Pick one..." /></SelectTrigger>',
    },
    "SelectContent": {
        "category": "forms",
        "description": "Dropdown panel containing SelectItems. Rendered in a portal.",
        "props": {
            "position": "\"popper\" | \"item-aligned\"",
            "align": "\"start\" | \"center\" | \"end\"",
        },
        "example": "<SelectContent><SelectItem value=\"a\">A</SelectItem></SelectContent>",
    },
    "SelectGroup": {
        "category": "forms",
        "description": "Group of related SelectItems, optionally with a SelectLabel.",
        "props": {},
        "example": "<SelectGroup><SelectLabel>Fruits</SelectLabel><SelectItem value=\"apple\">Apple</SelectItem></SelectGroup>",
    },
    "SelectItem": {
        "category": "forms",
        "description": "Individual option inside a Select dropdown.",
        "props": {
            "value": "string (required)",
            "disabled": "boolean",
        },
        "example": '<SelectItem value="active">Active</SelectItem>',
    },
    "SelectLabel": {
        "category": "forms",
        "description": "Non-selectable label for a SelectGroup.",
        "props": {},
        "example": "<SelectLabel>Category</SelectLabel>",
    },
    "SelectValue": {
        "category": "forms",
        "description": "Displays the selected value inside SelectTrigger.",
        "props": {
            "placeholder": "string",
        },
        "example": '<SelectValue placeholder="Choose..." />',
    },
    "SelectSeparator": {
        "category": "forms",
        "description": "Visual divider between groups in a Select dropdown.",
        "props": {},
        "example": "<SelectSeparator />",
    },
    "RadioGroup": {
        "category": "forms",
        "description": "Group of radio buttons for single selection.",
        "children": ["RadioGroupItem"],
        "props": {
            "value": "string",
            "onValueChange": "(value: string) => void",
            "defaultValue": "string",
        },
        "example": (
            '<RadioGroup value={plan} onValueChange={setPlan}>\n'
            '  <div className="flex items-center gap-2"><RadioGroupItem value="free" /><Label>Free</Label></div>\n'
            '  <div className="flex items-center gap-2"><RadioGroupItem value="pro" /><Label>Pro</Label></div>\n'
            '</RadioGroup>'
        ),
    },
    "RadioGroupItem": {
        "category": "forms",
        "description": "Individual radio button inside a RadioGroup.",
        "props": {
            "value": "string (required)",
            "disabled": "boolean",
        },
        "example": '<RadioGroupItem value="option1" />',
    },
    "Combobox": {
        "category": "forms",
        "description": "Searchable dropdown select. Takes an array of options with value/label.",
        "props": {
            "options": "Array<{ value: string; label: string; description?: string }>",
            "value": "string",
            "onValueChange": "(value: string) => void",
            "placeholder": "string",
            "searchPlaceholder": "string",
            "emptyText": "string",
            "disabled": "boolean",
            "isLoading": "boolean",
        },
        "example": (
            '<Combobox\n'
            '  options={[{ value: "us", label: "United States" }, { value: "uk", label: "United Kingdom" }]}\n'
            '  value={country}\n'
            '  onValueChange={setCountry}\n'
            '  placeholder="Select country..."\n'
            '/>'
        ),
    },
    "MultiCombobox": {
        "category": "forms",
        "description": "Multi-select searchable dropdown. Selected items shown as badges.",
        "props": {
            "options": "Array<{ value: string; label: string; description?: string }>",
            "value": "string[]",
            "onValueChange": "(values: string[]) => void",
            "placeholder": "string",
            "searchPlaceholder": "string",
            "emptyText": "string",
            "disabled": "boolean",
            "isLoading": "boolean",
            "maxDisplayedItems": "number",
        },
        "example": (
            '<MultiCombobox\n'
            '  options={tagOptions}\n'
            '  value={selectedTags}\n'
            '  onValueChange={setSelectedTags}\n'
            '  placeholder="Select tags..."\n'
            '/>'
        ),
    },
    "TagsInput": {
        "category": "forms",
        "description": "Tokenized input field. Add tags by pressing Space, Tab, Enter, or comma. Shows tags as badges.",
        "props": {
            "value": "string[]",
            "onChange": "(tags: string[]) => void",
            "placeholder": "string",
            "validate": "(tag: string) => boolean",
            "errorMessage": "string",
        },
        "example": (
            '<TagsInput\n'
            '  value={emails}\n'
            '  onChange={setEmails}\n'
            '  placeholder="Type email and press space..."\n'
            '  validate={(tag) => tag.includes("@")}\n'
            '  errorMessage="Must be a valid email"\n'
            '/>'
        ),
    },
    "Slider": {
        "category": "forms",
        "description": "Range slider for numeric values.",
        "props": {
            "value": "number[]",
            "onValueChange": "(value: number[]) => void",
            "min": "number",
            "max": "number",
            "step": "number",
            "disabled": "boolean",
        },
        "example": '<Slider value={[volume]} onValueChange={(v) => setVolume(v[0])} min={0} max={100} step={1} />',
    },

    # =========================================================================
    # Display
    # =========================================================================
    "Badge": {
        "category": "display",
        "description": "Small status label with color variants.",
        "props": {
            "variant": "\"default\" | \"secondary\" | \"destructive\" | \"outline\" | \"warning\"",
        },
        "example": '<Badge variant="secondary">Pending</Badge>',
    },
    "Avatar": {
        "category": "display",
        "description": "Circular user avatar with image and fallback.",
        "children": ["AvatarImage", "AvatarFallback"],
        "props": {
            "className": "string",
        },
        "example": (
            '<Avatar>\n'
            '  <AvatarImage src="/avatar.png" alt="User" />\n'
            '  <AvatarFallback>JD</AvatarFallback>\n'
            '</Avatar>'
        ),
    },
    "AvatarImage": {
        "category": "display",
        "description": "Image inside Avatar. Falls back to AvatarFallback on error.",
        "props": {
            "src": "string",
            "alt": "string",
        },
        "example": '<AvatarImage src="/photo.jpg" alt="John" />',
    },
    "AvatarFallback": {
        "category": "display",
        "description": "Fallback content shown when AvatarImage fails to load. Usually initials.",
        "props": {},
        "example": "<AvatarFallback>JD</AvatarFallback>",
    },
    "Alert": {
        "category": "display",
        "description": "Callout box for important messages with optional icon.",
        "children": ["AlertTitle", "AlertDescription"],
        "props": {
            "variant": "\"default\" | \"destructive\"",
        },
        "example": (
            '<Alert variant="destructive">\n'
            "  <AlertTitle>Error</AlertTitle>\n"
            "  <AlertDescription>Something went wrong.</AlertDescription>\n"
            "</Alert>"
        ),
    },
    "AlertTitle": {
        "category": "display",
        "description": "Title text inside an Alert.",
        "props": {},
        "example": "<AlertTitle>Warning</AlertTitle>",
    },
    "AlertDescription": {
        "category": "display",
        "description": "Description text inside an Alert.",
        "props": {},
        "example": "<AlertDescription>Please check your input.</AlertDescription>",
    },
    "Skeleton": {
        "category": "display",
        "description": "Animated placeholder for loading states. Style with className for width/height.",
        "props": {
            "className": "string - Use to set dimensions (e.g. \"h-8 w-48\")",
        },
        "example": '<Skeleton className="h-8 w-48" />',
    },
    "Progress": {
        "category": "display",
        "description": "Horizontal progress bar.",
        "props": {
            "value": "number - Progress percentage (0-100)",
        },
        "example": "<Progress value={75} />",
    },
    "Separator": {
        "category": "display",
        "description": "Visual divider line, horizontal or vertical.",
        "props": {
            "orientation": "\"horizontal\" | \"vertical\"",
            "decorative": "boolean (default true)",
        },
        "example": '<Separator className="my-4" />',
    },

    # =========================================================================
    # Navigation
    # =========================================================================
    "Tabs": {
        "category": "navigation",
        "description": "Tabbed navigation container. Compound component.",
        "children": ["TabsList", "TabsTrigger", "TabsContent"],
        "props": {
            "defaultValue": "string",
            "value": "string",
            "onValueChange": "(value: string) => void",
        },
        "example": (
            '<Tabs defaultValue="overview">\n'
            "  <TabsList>\n"
            '    <TabsTrigger value="overview">Overview</TabsTrigger>\n'
            '    <TabsTrigger value="settings">Settings</TabsTrigger>\n'
            "  </TabsList>\n"
            '  <TabsContent value="overview">Overview content</TabsContent>\n'
            '  <TabsContent value="settings">Settings content</TabsContent>\n'
            "</Tabs>"
        ),
    },
    "TabsList": {
        "category": "navigation",
        "description": "Container for TabsTrigger buttons. Renders a pill-shaped bar.",
        "props": {"className": "string"},
        "example": "<TabsList><TabsTrigger value=\"a\">A</TabsTrigger></TabsList>",
    },
    "TabsTrigger": {
        "category": "navigation",
        "description": "Individual tab button inside TabsList.",
        "props": {
            "value": "string (required)",
            "disabled": "boolean",
        },
        "example": '<TabsTrigger value="details">Details</TabsTrigger>',
    },
    "TabsContent": {
        "category": "navigation",
        "description": "Content panel shown when its tab is active.",
        "props": {
            "value": "string (required) - Must match a TabsTrigger value",
        },
        "example": '<TabsContent value="details">Tab content here</TabsContent>',
    },
    "Pagination": {
        "category": "navigation",
        "description": "Page navigation container.",
        "children": ["PaginationContent", "PaginationEllipsis", "PaginationItem", "PaginationLink", "PaginationNext", "PaginationPrevious"],
        "props": {},
        "example": (
            "<Pagination>\n"
            "  <PaginationContent>\n"
            "    <PaginationItem><PaginationPrevious onClick={prevPage} /></PaginationItem>\n"
            '    <PaginationItem><PaginationLink isActive>1</PaginationLink></PaginationItem>\n'
            "    <PaginationItem><PaginationLink>2</PaginationLink></PaginationItem>\n"
            "    <PaginationItem><PaginationEllipsis /></PaginationItem>\n"
            "    <PaginationItem><PaginationNext onClick={nextPage} /></PaginationItem>\n"
            "  </PaginationContent>\n"
            "</Pagination>"
        ),
    },
    "PaginationContent": {
        "category": "navigation",
        "description": "Flex container for PaginationItems.",
        "props": {},
        "example": "<PaginationContent>...</PaginationContent>",
    },
    "PaginationItem": {
        "category": "navigation",
        "description": "Wrapper <li> for each pagination element.",
        "props": {},
        "example": "<PaginationItem><PaginationLink>1</PaginationLink></PaginationItem>",
    },
    "PaginationLink": {
        "category": "navigation",
        "description": "Clickable page number link.",
        "props": {
            "isActive": "boolean - Highlights the current page",
            "size": "\"default\" | \"sm\" | \"lg\" | \"icon\"",
        },
        "example": "<PaginationLink isActive>1</PaginationLink>",
    },
    "PaginationPrevious": {
        "category": "navigation",
        "description": "Previous page button with chevron icon.",
        "props": {"onClick": "() => void"},
        "example": "<PaginationPrevious onClick={goBack} />",
    },
    "PaginationNext": {
        "category": "navigation",
        "description": "Next page button with chevron icon.",
        "props": {"onClick": "() => void"},
        "example": "<PaginationNext onClick={goForward} />",
    },
    "PaginationEllipsis": {
        "category": "navigation",
        "description": "Ellipsis indicator (...) for skipped pages.",
        "props": {},
        "example": "<PaginationEllipsis />",
    },

    # =========================================================================
    # Feedback & Overlay - Dialog
    # =========================================================================
    "Dialog": {
        "category": "feedback",
        "description": "Modal dialog overlay. Compound component with trigger and content.",
        "children": ["DialogClose", "DialogContent", "DialogDescription", "DialogFooter", "DialogHeader", "DialogTitle", "DialogTrigger"],
        "props": {
            "open": "boolean",
            "onOpenChange": "(open: boolean) => void",
        },
        "example": (
            "<Dialog open={open} onOpenChange={setOpen}>\n"
            "  <DialogTrigger asChild><Button>Open</Button></DialogTrigger>\n"
            "  <DialogContent>\n"
            "    <DialogHeader>\n"
            "      <DialogTitle>Edit Item</DialogTitle>\n"
            "      <DialogDescription>Make changes below.</DialogDescription>\n"
            "    </DialogHeader>\n"
            "    <div>Form content here</div>\n"
            "    <DialogFooter><Button onClick={save}>Save</Button></DialogFooter>\n"
            "  </DialogContent>\n"
            "</Dialog>"
        ),
    },
    "DialogTrigger": {
        "category": "feedback",
        "description": "Element that opens the Dialog when clicked.",
        "props": {"asChild": "boolean"},
        "example": "<DialogTrigger asChild><Button>Open Dialog</Button></DialogTrigger>",
    },
    "DialogContent": {
        "category": "feedback",
        "description": "Modal container with overlay, centered on screen. Max width lg, max height 90vh with scroll.",
        "props": {
            "showCloseButton": "boolean (default true)",
            "className": "string",
        },
        "example": "<DialogContent>...</DialogContent>",
    },
    "DialogHeader": {
        "category": "feedback",
        "description": "Header section inside DialogContent for title and description.",
        "props": {},
        "example": "<DialogHeader><DialogTitle>Title</DialogTitle></DialogHeader>",
    },
    "DialogTitle": {
        "category": "feedback",
        "description": "Title text inside DialogHeader.",
        "props": {},
        "example": "<DialogTitle>Confirm Action</DialogTitle>",
    },
    "DialogDescription": {
        "category": "feedback",
        "description": "Description text inside DialogHeader.",
        "props": {},
        "example": "<DialogDescription>This action cannot be undone.</DialogDescription>",
    },
    "DialogFooter": {
        "category": "feedback",
        "description": "Footer section for action buttons. Uses flex-row on sm+ screens.",
        "props": {},
        "example": "<DialogFooter><Button variant=\"outline\">Cancel</Button><Button>Confirm</Button></DialogFooter>",
    },
    "DialogClose": {
        "category": "feedback",
        "description": "Button that closes the Dialog when clicked.",
        "props": {"asChild": "boolean"},
        "example": "<DialogClose asChild><Button variant=\"outline\">Cancel</Button></DialogClose>",
    },

    # =========================================================================
    # Feedback & Overlay - AlertDialog
    # =========================================================================
    "AlertDialog": {
        "category": "feedback",
        "description": "Confirmation dialog that requires explicit user action. Cannot be dismissed by clicking outside.",
        "children": ["AlertDialogTrigger", "AlertDialogContent", "AlertDialogHeader", "AlertDialogFooter", "AlertDialogTitle", "AlertDialogDescription", "AlertDialogAction", "AlertDialogCancel"],
        "props": {
            "open": "boolean",
            "onOpenChange": "(open: boolean) => void",
        },
        "example": (
            "<AlertDialog>\n"
            "  <AlertDialogTrigger asChild><Button variant=\"destructive\">Delete</Button></AlertDialogTrigger>\n"
            "  <AlertDialogContent>\n"
            "    <AlertDialogHeader>\n"
            "      <AlertDialogTitle>Are you sure?</AlertDialogTitle>\n"
            "      <AlertDialogDescription>This cannot be undone.</AlertDialogDescription>\n"
            "    </AlertDialogHeader>\n"
            "    <AlertDialogFooter>\n"
            "      <AlertDialogCancel>Cancel</AlertDialogCancel>\n"
            "      <AlertDialogAction onClick={handleDelete}>Delete</AlertDialogAction>\n"
            "    </AlertDialogFooter>\n"
            "  </AlertDialogContent>\n"
            "</AlertDialog>"
        ),
    },
    "AlertDialogTrigger": {
        "category": "feedback",
        "description": "Element that opens the AlertDialog.",
        "props": {"asChild": "boolean"},
        "example": "<AlertDialogTrigger asChild><Button>Delete</Button></AlertDialogTrigger>",
    },
    "AlertDialogContent": {
        "category": "feedback",
        "description": "Modal content container for AlertDialog.",
        "props": {"className": "string"},
        "example": "<AlertDialogContent>...</AlertDialogContent>",
    },
    "AlertDialogHeader": {
        "category": "feedback",
        "description": "Header section for AlertDialog title and description.",
        "props": {},
        "example": "<AlertDialogHeader><AlertDialogTitle>Title</AlertDialogTitle></AlertDialogHeader>",
    },
    "AlertDialogTitle": {
        "category": "feedback",
        "description": "Title of the AlertDialog.",
        "props": {},
        "example": "<AlertDialogTitle>Confirm Deletion</AlertDialogTitle>",
    },
    "AlertDialogDescription": {
        "category": "feedback",
        "description": "Description text for AlertDialog.",
        "props": {},
        "example": "<AlertDialogDescription>This will permanently delete the item.</AlertDialogDescription>",
    },
    "AlertDialogFooter": {
        "category": "feedback",
        "description": "Footer for AlertDialog action buttons.",
        "props": {},
        "example": "<AlertDialogFooter><AlertDialogCancel>Cancel</AlertDialogCancel><AlertDialogAction>OK</AlertDialogAction></AlertDialogFooter>",
    },
    "AlertDialogAction": {
        "category": "feedback",
        "description": "Confirm button that closes the AlertDialog.",
        "props": {"onClick": "() => void"},
        "example": "<AlertDialogAction onClick={handleConfirm}>Continue</AlertDialogAction>",
    },
    "AlertDialogCancel": {
        "category": "feedback",
        "description": "Cancel button that closes the AlertDialog.",
        "props": {},
        "example": "<AlertDialogCancel>Cancel</AlertDialogCancel>",
    },

    # =========================================================================
    # Feedback & Overlay - Tooltip
    # =========================================================================
    "Tooltip": {
        "category": "feedback",
        "description": "Hover tooltip popup. Must be wrapped in TooltipProvider.",
        "children": ["TooltipContent", "TooltipProvider", "TooltipTrigger"],
        "props": {},
        "example": (
            "<TooltipProvider>\n"
            "  <Tooltip>\n"
            "    <TooltipTrigger asChild><Button variant=\"icon\"><InfoIcon /></Button></TooltipTrigger>\n"
            '    <TooltipContent>Helpful information</TooltipContent>\n'
            "  </Tooltip>\n"
            "</TooltipProvider>"
        ),
    },
    "TooltipProvider": {
        "category": "feedback",
        "description": "Context provider for Tooltip. Wrap around Tooltip usage.",
        "props": {
            "delayDuration": "number (ms before showing)",
        },
        "example": "<TooltipProvider delayDuration={200}>...</TooltipProvider>",
    },
    "TooltipTrigger": {
        "category": "feedback",
        "description": "Element that triggers the Tooltip on hover.",
        "props": {"asChild": "boolean"},
        "example": "<TooltipTrigger asChild><span>Hover me</span></TooltipTrigger>",
    },
    "TooltipContent": {
        "category": "feedback",
        "description": "Popup content of the Tooltip.",
        "props": {
            "side": "\"top\" | \"right\" | \"bottom\" | \"left\"",
            "align": "\"start\" | \"center\" | \"end\"",
        },
        "example": '<TooltipContent side="top">Tooltip text</TooltipContent>',
    },

    # =========================================================================
    # Feedback & Overlay - Popover
    # =========================================================================
    "Popover": {
        "category": "feedback",
        "description": "Click-triggered floating panel. More flexible than Tooltip -- supports interactive content.",
        "children": ["PopoverContent", "PopoverTrigger", "PopoverAnchor"],
        "props": {
            "open": "boolean",
            "onOpenChange": "(open: boolean) => void",
        },
        "example": (
            "<Popover>\n"
            "  <PopoverTrigger asChild><Button>Open</Button></PopoverTrigger>\n"
            "  <PopoverContent>Interactive content here</PopoverContent>\n"
            "</Popover>"
        ),
    },
    "PopoverTrigger": {
        "category": "feedback",
        "description": "Element that toggles the Popover.",
        "props": {"asChild": "boolean"},
        "example": "<PopoverTrigger asChild><Button>Show</Button></PopoverTrigger>",
    },
    "PopoverContent": {
        "category": "feedback",
        "description": "Floating panel content for Popover.",
        "props": {
            "side": "\"top\" | \"right\" | \"bottom\" | \"left\"",
            "align": "\"start\" | \"center\" | \"end\"",
            "className": "string",
        },
        "example": '<PopoverContent align="start">Content</PopoverContent>',
    },
    "PopoverAnchor": {
        "category": "feedback",
        "description": "Custom anchor point for Popover positioning.",
        "props": {"asChild": "boolean"},
        "example": "<PopoverAnchor asChild><div ref={anchorRef} /></PopoverAnchor>",
    },

    # =========================================================================
    # Feedback & Overlay - HoverCard
    # =========================================================================
    "HoverCard": {
        "category": "feedback",
        "description": "Card that appears on hover. Useful for link previews.",
        "children": ["HoverCardContent", "HoverCardTrigger"],
        "props": {
            "openDelay": "number",
            "closeDelay": "number",
        },
        "example": (
            "<HoverCard>\n"
            "  <HoverCardTrigger asChild><Link to=\"/user\">@john</Link></HoverCardTrigger>\n"
            "  <HoverCardContent>User profile preview</HoverCardContent>\n"
            "</HoverCard>"
        ),
    },
    "HoverCardTrigger": {
        "category": "feedback",
        "description": "Element that triggers the HoverCard on hover.",
        "props": {"asChild": "boolean"},
        "example": "<HoverCardTrigger asChild><span>Hover me</span></HoverCardTrigger>",
    },
    "HoverCardContent": {
        "category": "feedback",
        "description": "Content panel of the HoverCard.",
        "props": {
            "side": "\"top\" | \"right\" | \"bottom\" | \"left\"",
            "align": "\"start\" | \"center\" | \"end\"",
        },
        "example": "<HoverCardContent>Preview info</HoverCardContent>",
    },

    # =========================================================================
    # Feedback & Overlay - Sheet
    # =========================================================================
    "Sheet": {
        "category": "feedback",
        "description": "Slide-out panel (drawer) from screen edge. Good for forms and detail views.",
        "children": ["SheetClose", "SheetContent", "SheetDescription", "SheetFooter", "SheetHeader", "SheetTitle", "SheetTrigger"],
        "props": {
            "open": "boolean",
            "onOpenChange": "(open: boolean) => void",
        },
        "example": (
            "<Sheet open={open} onOpenChange={setOpen}>\n"
            "  <SheetTrigger asChild><Button>Open Panel</Button></SheetTrigger>\n"
            '  <SheetContent side="right">\n'
            "    <SheetHeader>\n"
            "      <SheetTitle>Edit Profile</SheetTitle>\n"
            "      <SheetDescription>Make changes here.</SheetDescription>\n"
            "    </SheetHeader>\n"
            "    <div>Form content</div>\n"
            "  </SheetContent>\n"
            "</Sheet>"
        ),
    },
    "SheetTrigger": {
        "category": "feedback",
        "description": "Element that opens the Sheet.",
        "props": {"asChild": "boolean"},
        "example": "<SheetTrigger asChild><Button>Open</Button></SheetTrigger>",
    },
    "SheetContent": {
        "category": "feedback",
        "description": "Slide-out panel content. Slides from a screen edge.",
        "props": {
            "side": "\"top\" | \"right\" | \"bottom\" | \"left\"",
            "className": "string",
        },
        "example": '<SheetContent side="right">...</SheetContent>',
    },
    "SheetHeader": {
        "category": "feedback",
        "description": "Header section of Sheet.",
        "props": {},
        "example": "<SheetHeader><SheetTitle>Title</SheetTitle></SheetHeader>",
    },
    "SheetTitle": {
        "category": "feedback",
        "description": "Title text inside SheetHeader.",
        "props": {},
        "example": "<SheetTitle>Panel Title</SheetTitle>",
    },
    "SheetDescription": {
        "category": "feedback",
        "description": "Description text inside SheetHeader.",
        "props": {},
        "example": "<SheetDescription>Helper text</SheetDescription>",
    },
    "SheetFooter": {
        "category": "feedback",
        "description": "Footer section of Sheet for action buttons.",
        "props": {},
        "example": "<SheetFooter><Button>Save</Button></SheetFooter>",
    },
    "SheetClose": {
        "category": "feedback",
        "description": "Button that closes the Sheet.",
        "props": {"asChild": "boolean"},
        "example": "<SheetClose asChild><Button variant=\"outline\">Close</Button></SheetClose>",
    },

    # =========================================================================
    # Feedback & Overlay - Command
    # =========================================================================
    "Command": {
        "category": "feedback",
        "description": "Command palette / searchable list. Used internally by Combobox, but can be used standalone.",
        "children": ["CommandDialog", "CommandEmpty", "CommandGroup", "CommandInput", "CommandItem", "CommandList", "CommandSeparator", "CommandShortcut"],
        "props": {},
        "example": (
            "<Command>\n"
            '  <CommandInput placeholder="Search..." />\n'
            "  <CommandList>\n"
            "    <CommandEmpty>No results.</CommandEmpty>\n"
            "    <CommandGroup heading=\"Actions\">\n"
            '      <CommandItem>New File</CommandItem>\n'
            '      <CommandItem>Settings</CommandItem>\n'
            "    </CommandGroup>\n"
            "  </CommandList>\n"
            "</Command>"
        ),
    },
    "CommandDialog": {
        "category": "feedback",
        "description": "Command palette inside a Dialog overlay.",
        "props": {
            "open": "boolean",
            "onOpenChange": "(open: boolean) => void",
        },
        "example": "<CommandDialog open={open} onOpenChange={setOpen}>...</CommandDialog>",
    },
    "CommandInput": {
        "category": "feedback",
        "description": "Search input for filtering Command items.",
        "props": {"placeholder": "string"},
        "example": '<CommandInput placeholder="Type to search..." />',
    },
    "CommandList": {
        "category": "feedback",
        "description": "Scrollable list container for CommandGroups and CommandItems.",
        "props": {"className": "string"},
        "example": "<CommandList>...</CommandList>",
    },
    "CommandEmpty": {
        "category": "feedback",
        "description": "Shown when no CommandItems match the search.",
        "props": {},
        "example": "<CommandEmpty>No results found.</CommandEmpty>",
    },
    "CommandGroup": {
        "category": "feedback",
        "description": "Group of CommandItems with optional heading.",
        "props": {"heading": "string"},
        "example": "<CommandGroup heading=\"Suggestions\"><CommandItem>Item</CommandItem></CommandGroup>",
    },
    "CommandItem": {
        "category": "feedback",
        "description": "Individual selectable item in a Command list.",
        "props": {
            "value": "string",
            "onSelect": "(value: string) => void",
            "disabled": "boolean",
            "keywords": "string[] - Additional search keywords",
        },
        "example": '<CommandItem value="settings" onSelect={() => navigate("/settings")}>Settings</CommandItem>',
    },
    "CommandSeparator": {
        "category": "feedback",
        "description": "Visual divider between CommandGroups.",
        "props": {},
        "example": "<CommandSeparator />",
    },
    "CommandShortcut": {
        "category": "feedback",
        "description": "Keyboard shortcut hint text, right-aligned inside CommandItem.",
        "props": {},
        "example": "<CommandShortcut>Ctrl+K</CommandShortcut>",
    },

    # =========================================================================
    # Feedback & Overlay - ContextMenu
    # =========================================================================
    "ContextMenu": {
        "category": "feedback",
        "description": "Right-click context menu. Triggered by right-clicking the trigger area.",
        "children": [
            "ContextMenuCheckboxItem", "ContextMenuContent", "ContextMenuGroup",
            "ContextMenuItem", "ContextMenuLabel", "ContextMenuPortal",
            "ContextMenuRadioGroup", "ContextMenuRadioItem", "ContextMenuSeparator",
            "ContextMenuShortcut", "ContextMenuSub", "ContextMenuSubContent",
            "ContextMenuSubTrigger", "ContextMenuTrigger",
        ],
        "props": {},
        "example": (
            "<ContextMenu>\n"
            "  <ContextMenuTrigger>Right click here</ContextMenuTrigger>\n"
            "  <ContextMenuContent>\n"
            "    <ContextMenuItem>Copy</ContextMenuItem>\n"
            "    <ContextMenuItem>Paste</ContextMenuItem>\n"
            "    <ContextMenuSeparator />\n"
            "    <ContextMenuItem>Delete</ContextMenuItem>\n"
            "  </ContextMenuContent>\n"
            "</ContextMenu>"
        ),
    },
    "ContextMenuTrigger": {
        "category": "feedback",
        "description": "Area that responds to right-click to open the ContextMenu.",
        "props": {},
        "example": '<ContextMenuTrigger className="w-full h-full">Right click area</ContextMenuTrigger>',
    },
    "ContextMenuContent": {
        "category": "feedback",
        "description": "Dropdown menu content for ContextMenu.",
        "props": {"className": "string"},
        "example": "<ContextMenuContent><ContextMenuItem>Action</ContextMenuItem></ContextMenuContent>",
    },
    "ContextMenuGroup": {
        "category": "feedback",
        "description": "Group of related ContextMenuItems.",
        "props": {},
        "example": "<ContextMenuGroup><ContextMenuItem>Item 1</ContextMenuItem></ContextMenuGroup>",
    },
    "ContextMenuItem": {
        "category": "feedback",
        "description": "Individual action item in a ContextMenu.",
        "props": {
            "onSelect": "() => void",
            "disabled": "boolean",
        },
        "example": '<ContextMenuItem onSelect={handleCopy}>Copy</ContextMenuItem>',
    },
    "ContextMenuLabel": {
        "category": "feedback",
        "description": "Non-interactive label in a ContextMenu.",
        "props": {},
        "example": "<ContextMenuLabel>Actions</ContextMenuLabel>",
    },
    "ContextMenuSeparator": {
        "category": "feedback",
        "description": "Visual divider in a ContextMenu.",
        "props": {},
        "example": "<ContextMenuSeparator />",
    },
    "ContextMenuShortcut": {
        "category": "feedback",
        "description": "Keyboard shortcut display in a ContextMenuItem.",
        "props": {},
        "example": "<ContextMenuShortcut>Ctrl+C</ContextMenuShortcut>",
    },
    "ContextMenuCheckboxItem": {
        "category": "feedback",
        "description": "Checkbox item inside a ContextMenu.",
        "props": {
            "checked": "boolean",
            "onCheckedChange": "(checked: boolean) => void",
        },
        "example": '<ContextMenuCheckboxItem checked={showGrid} onCheckedChange={setShowGrid}>Show Grid</ContextMenuCheckboxItem>',
    },
    "ContextMenuRadioGroup": {
        "category": "feedback",
        "description": "Radio group inside a ContextMenu for single selection.",
        "props": {
            "value": "string",
            "onValueChange": "(value: string) => void",
        },
        "example": '<ContextMenuRadioGroup value={view} onValueChange={setView}>...</ContextMenuRadioGroup>',
    },
    "ContextMenuRadioItem": {
        "category": "feedback",
        "description": "Radio item inside a ContextMenuRadioGroup.",
        "props": {"value": "string (required)"},
        "example": '<ContextMenuRadioItem value="grid">Grid View</ContextMenuRadioItem>',
    },
    "ContextMenuPortal": {
        "category": "feedback",
        "description": "Portal for rendering ContextMenu content outside the DOM tree.",
        "props": {},
        "example": "<ContextMenuPortal><ContextMenuSubContent>...</ContextMenuSubContent></ContextMenuPortal>",
    },
    "ContextMenuSub": {
        "category": "feedback",
        "description": "Submenu container inside a ContextMenu.",
        "props": {},
        "example": "<ContextMenuSub><ContextMenuSubTrigger>More</ContextMenuSubTrigger><ContextMenuSubContent>...</ContextMenuSubContent></ContextMenuSub>",
    },
    "ContextMenuSubTrigger": {
        "category": "feedback",
        "description": "Trigger that opens a ContextMenu submenu.",
        "props": {},
        "example": "<ContextMenuSubTrigger>More Actions</ContextMenuSubTrigger>",
    },
    "ContextMenuSubContent": {
        "category": "feedback",
        "description": "Content of a ContextMenu submenu.",
        "props": {},
        "example": "<ContextMenuSubContent><ContextMenuItem>Sub Item</ContextMenuItem></ContextMenuSubContent>",
    },

    # =========================================================================
    # Data & Tables
    # =========================================================================
    "Table": {
        "category": "data",
        "description": "HTML table with styled appearance. Wrapped in a scrollable container.",
        "children": ["TableHeader", "TableBody", "TableFooter", "TableHead", "TableRow", "TableCell", "TableCaption"],
        "props": {"className": "string"},
        "example": (
            "<Table>\n"
            "  <TableHeader>\n"
            "    <TableRow>\n"
            "      <TableHead>Name</TableHead>\n"
            "      <TableHead>Email</TableHead>\n"
            "    </TableRow>\n"
            "  </TableHeader>\n"
            "  <TableBody>\n"
            "    {items.map(item => (\n"
            "      <TableRow key={item.id}>\n"
            "        <TableCell>{item.name}</TableCell>\n"
            "        <TableCell>{item.email}</TableCell>\n"
            "      </TableRow>\n"
            "    ))}\n"
            "  </TableBody>\n"
            "</Table>"
        ),
    },
    "TableHeader": {
        "category": "data",
        "description": "Table header section (<thead>). Contains TableRow with TableHead cells.",
        "props": {},
        "example": "<TableHeader><TableRow><TableHead>Column</TableHead></TableRow></TableHeader>",
    },
    "TableBody": {
        "category": "data",
        "description": "Table body section (<tbody>). Contains TableRows with TableCells.",
        "props": {},
        "example": "<TableBody><TableRow><TableCell>Data</TableCell></TableRow></TableBody>",
    },
    "TableFooter": {
        "category": "data",
        "description": "Table footer section (<tfoot>). Styled with muted background.",
        "props": {},
        "example": "<TableFooter><TableRow><TableCell>Total</TableCell></TableRow></TableFooter>",
    },
    "TableRow": {
        "category": "data",
        "description": "Table row (<tr>). Has hover highlighting and border.",
        "props": {"className": "string"},
        "example": "<TableRow><TableCell>Cell</TableCell></TableRow>",
    },
    "TableHead": {
        "category": "data",
        "description": "Table header cell (<th>). Left-aligned, medium font weight.",
        "props": {"className": "string"},
        "example": "<TableHead>Column Name</TableHead>",
    },
    "TableCell": {
        "category": "data",
        "description": "Table data cell (<td>).",
        "props": {"className": "string"},
        "example": "<TableCell>Cell content</TableCell>",
    },
    "TableCaption": {
        "category": "data",
        "description": "Table caption text. Displayed below the table.",
        "props": {},
        "example": "<TableCaption>A list of recent invoices.</TableCaption>",
    },

    # =========================================================================
    # Calendar / Date
    # =========================================================================
    "Calendar": {
        "category": "forms",
        "description": "Date picker calendar. Based on react-day-picker. Use inside a Popover for dropdown date selection.",
        "props": {
            "mode": "\"single\" | \"multiple\" | \"range\"",
            "selected": "Date | Date[] | DateRange",
            "onSelect": "(date: Date | DateRange) => void",
            "disabled": "boolean | (date: Date) => boolean",
            "showOutsideDays": "boolean (default true)",
        },
        "example": '<Calendar mode="single" selected={date} onSelect={setDate} />',
    },
    "DateRangePicker": {
        "category": "forms",
        "description": "Pre-built date range picker with popover calendar and clear button.",
        "props": {
            "dateRange": "{ from: Date; to: Date } | undefined",
            "onDateRangeChange": "(range: { from: Date; to: Date } | undefined) => void",
            "className": "string",
        },
        "example": '<DateRangePicker dateRange={range} onDateRangeChange={setRange} />',
    },

    # =========================================================================
    # Accordion / Collapsible
    # =========================================================================
    "Accordion": {
        "category": "display",
        "description": "Expandable section list. Can be single or multiple open at once.",
        "children": ["AccordionContent", "AccordionItem", "AccordionTrigger"],
        "props": {
            "type": "\"single\" | \"multiple\"",
            "collapsible": "boolean (for type=\"single\")",
            "defaultValue": "string | string[]",
        },
        "example": (
            '<Accordion type="single" collapsible>\n'
            '  <AccordionItem value="item-1">\n'
            "    <AccordionTrigger>Section 1</AccordionTrigger>\n"
            "    <AccordionContent>Content for section 1</AccordionContent>\n"
            "  </AccordionItem>\n"
            '  <AccordionItem value="item-2">\n'
            "    <AccordionTrigger>Section 2</AccordionTrigger>\n"
            "    <AccordionContent>Content for section 2</AccordionContent>\n"
            "  </AccordionItem>\n"
            "</Accordion>"
        ),
    },
    "AccordionItem": {
        "category": "display",
        "description": "Individual expandable section in an Accordion.",
        "props": {"value": "string (required)"},
        "example": '<AccordionItem value="section-1">...</AccordionItem>',
    },
    "AccordionTrigger": {
        "category": "display",
        "description": "Clickable header that expands/collapses an AccordionItem. Shows a chevron.",
        "props": {},
        "example": "<AccordionTrigger>Click to expand</AccordionTrigger>",
    },
    "AccordionContent": {
        "category": "display",
        "description": "Collapsible content area of an AccordionItem. Animated open/close.",
        "props": {},
        "example": "<AccordionContent>Expanded content here</AccordionContent>",
    },
    "Collapsible": {
        "category": "display",
        "description": "Simple collapsible section with trigger and content.",
        "children": ["CollapsibleContent", "CollapsibleTrigger"],
        "props": {
            "open": "boolean",
            "onOpenChange": "(open: boolean) => void",
        },
        "example": (
            "<Collapsible open={open} onOpenChange={setOpen}>\n"
            "  <CollapsibleTrigger asChild><Button variant=\"ghost\">Toggle</Button></CollapsibleTrigger>\n"
            "  <CollapsibleContent>Hidden content revealed</CollapsibleContent>\n"
            "</Collapsible>"
        ),
    },
    "CollapsibleTrigger": {
        "category": "display",
        "description": "Element that toggles the Collapsible open/closed.",
        "props": {"asChild": "boolean"},
        "example": "<CollapsibleTrigger>Toggle</CollapsibleTrigger>",
    },
    "CollapsibleContent": {
        "category": "display",
        "description": "Content that is shown/hidden by the Collapsible.",
        "props": {},
        "example": "<CollapsibleContent>Collapsible body</CollapsibleContent>",
    },

    # =========================================================================
    # Toggle
    # =========================================================================
    "Toggle": {
        "category": "forms",
        "description": "Two-state toggle button (on/off). Like a styled checkbox button.",
        "props": {
            "variant": "\"default\" | \"outline\"",
            "size": "\"default\" | \"sm\" | \"lg\"",
            "pressed": "boolean",
            "onPressedChange": "(pressed: boolean) => void",
        },
        "example": '<Toggle pressed={bold} onPressedChange={setBold} variant="outline"><BoldIcon /></Toggle>',
    },
    "ToggleGroup": {
        "category": "forms",
        "description": "Group of Toggle buttons for single or multiple selection.",
        "children": ["ToggleGroupItem"],
        "props": {
            "type": "\"single\" | \"multiple\"",
            "value": "string | string[]",
            "onValueChange": "(value: string | string[]) => void",
            "variant": "\"default\" | \"outline\"",
            "size": "\"default\" | \"sm\" | \"lg\"",
        },
        "example": (
            '<ToggleGroup type="single" value={alignment} onValueChange={setAlignment}>\n'
            '  <ToggleGroupItem value="left"><AlignLeftIcon /></ToggleGroupItem>\n'
            '  <ToggleGroupItem value="center"><AlignCenterIcon /></ToggleGroupItem>\n'
            '  <ToggleGroupItem value="right"><AlignRightIcon /></ToggleGroupItem>\n'
            "</ToggleGroup>"
        ),
    },
    "ToggleGroupItem": {
        "category": "forms",
        "description": "Individual toggle button inside a ToggleGroup.",
        "props": {
            "value": "string (required)",
            "disabled": "boolean",
        },
        "example": '<ToggleGroupItem value="bold"><BoldIcon /></ToggleGroupItem>',
    },

    # =========================================================================
    # DropdownMenu
    # =========================================================================
    "DropdownMenu": {
        "category": "feedback",
        "description": "Click-triggered dropdown menu. For actions/options menus.",
        "children": [
            "DropdownMenuCheckboxItem", "DropdownMenuContent", "DropdownMenuGroup",
            "DropdownMenuItem", "DropdownMenuLabel", "DropdownMenuPortal",
            "DropdownMenuRadioGroup", "DropdownMenuRadioItem", "DropdownMenuSeparator",
            "DropdownMenuShortcut", "DropdownMenuSub", "DropdownMenuSubContent",
            "DropdownMenuSubTrigger", "DropdownMenuTrigger",
        ],
        "props": {},
        "example": (
            "<DropdownMenu>\n"
            "  <DropdownMenuTrigger asChild><Button variant=\"ghost\"><MoreHorizontal /></Button></DropdownMenuTrigger>\n"
            "  <DropdownMenuContent align=\"end\">\n"
            "    <DropdownMenuLabel>Actions</DropdownMenuLabel>\n"
            "    <DropdownMenuSeparator />\n"
            "    <DropdownMenuItem onClick={handleEdit}>Edit</DropdownMenuItem>\n"
            '    <DropdownMenuItem className="text-destructive" onClick={handleDelete}>Delete</DropdownMenuItem>\n'
            "  </DropdownMenuContent>\n"
            "</DropdownMenu>"
        ),
    },
    "DropdownMenuTrigger": {
        "category": "feedback",
        "description": "Element that opens the DropdownMenu when clicked.",
        "props": {"asChild": "boolean"},
        "example": "<DropdownMenuTrigger asChild><Button>Options</Button></DropdownMenuTrigger>",
    },
    "DropdownMenuContent": {
        "category": "feedback",
        "description": "Dropdown panel containing menu items.",
        "props": {
            "align": "\"start\" | \"center\" | \"end\"",
            "side": "\"top\" | \"right\" | \"bottom\" | \"left\"",
            "className": "string",
        },
        "example": '<DropdownMenuContent align="end">...</DropdownMenuContent>',
    },
    "DropdownMenuGroup": {
        "category": "feedback",
        "description": "Group of related DropdownMenuItems.",
        "props": {},
        "example": "<DropdownMenuGroup><DropdownMenuItem>Item</DropdownMenuItem></DropdownMenuGroup>",
    },
    "DropdownMenuItem": {
        "category": "feedback",
        "description": "Individual action item in a DropdownMenu.",
        "props": {
            "onClick": "() => void",
            "disabled": "boolean",
        },
        "example": "<DropdownMenuItem onClick={handleEdit}>Edit</DropdownMenuItem>",
    },
    "DropdownMenuLabel": {
        "category": "feedback",
        "description": "Non-interactive label in a DropdownMenu.",
        "props": {},
        "example": "<DropdownMenuLabel>My Account</DropdownMenuLabel>",
    },
    "DropdownMenuSeparator": {
        "category": "feedback",
        "description": "Visual divider in a DropdownMenu.",
        "props": {},
        "example": "<DropdownMenuSeparator />",
    },
    "DropdownMenuShortcut": {
        "category": "feedback",
        "description": "Keyboard shortcut hint in a DropdownMenuItem.",
        "props": {},
        "example": "<DropdownMenuShortcut>Ctrl+S</DropdownMenuShortcut>",
    },
    "DropdownMenuCheckboxItem": {
        "category": "feedback",
        "description": "Checkbox item in a DropdownMenu.",
        "props": {
            "checked": "boolean",
            "onCheckedChange": "(checked: boolean) => void",
        },
        "example": '<DropdownMenuCheckboxItem checked={showPanel} onCheckedChange={setShowPanel}>Show Panel</DropdownMenuCheckboxItem>',
    },
    "DropdownMenuRadioGroup": {
        "category": "feedback",
        "description": "Radio group inside a DropdownMenu.",
        "props": {
            "value": "string",
            "onValueChange": "(value: string) => void",
        },
        "example": '<DropdownMenuRadioGroup value={sortBy} onValueChange={setSortBy}>...</DropdownMenuRadioGroup>',
    },
    "DropdownMenuRadioItem": {
        "category": "feedback",
        "description": "Radio item inside a DropdownMenuRadioGroup.",
        "props": {"value": "string (required)"},
        "example": '<DropdownMenuRadioItem value="name">Sort by Name</DropdownMenuRadioItem>',
    },
    "DropdownMenuPortal": {
        "category": "feedback",
        "description": "Portal for rendering DropdownMenu submenu content.",
        "props": {},
        "example": "<DropdownMenuPortal><DropdownMenuSubContent>...</DropdownMenuSubContent></DropdownMenuPortal>",
    },
    "DropdownMenuSub": {
        "category": "feedback",
        "description": "Submenu container in a DropdownMenu.",
        "props": {},
        "example": "<DropdownMenuSub><DropdownMenuSubTrigger>More</DropdownMenuSubTrigger><DropdownMenuSubContent>...</DropdownMenuSubContent></DropdownMenuSub>",
    },
    "DropdownMenuSubTrigger": {
        "category": "feedback",
        "description": "Trigger that opens a DropdownMenu submenu.",
        "props": {},
        "example": "<DropdownMenuSubTrigger>More Options</DropdownMenuSubTrigger>",
    },
    "DropdownMenuSubContent": {
        "category": "feedback",
        "description": "Content of a DropdownMenu submenu.",
        "props": {},
        "example": "<DropdownMenuSubContent><DropdownMenuItem>Sub Item</DropdownMenuItem></DropdownMenuSubContent>",
    },
}
