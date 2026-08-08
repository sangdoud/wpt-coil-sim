oProject = oDesktop.GetActiveProject()
oDesign = oProject.GetActiveDesign()
oEditor = oDesign.SetActiveEditor("3D Modeler")
oEditor.CreateRectangle(
	[
		"NAME:RectangleParameters",
		"IsCovered:="		, True,
		"XStart:="		, "0.2mm",
		"YStart:="		, "0mm",
		"ZStart:="		, "-0.1mm",
		"Width:="		, "-0.1mm",
		"Height:="		, "0.3mm",
		"WhichAxis:="		, "Y"
	], 
	[
		"NAME:Attributes",
		"Name:="		, "Rectangle1",
		"Flags:="		, "",
		"Color:="		, "(143 175 143)",
		"Transparency:="	, 0,
		"PartCoordinateSystem:=", "Global",
		"UDMId:="		, "",
		"MaterialValue:="	, "\"vacuum\"",
		"SurfaceMaterialValue:=", "\"\"",
		"SolveInside:="		, True,
		"ShellElement:="	, False,
		"ShellElementThickness:=", "0mm",
		"ReferenceTemperature:=", "20cel",
		"IsMaterialEditable:="	, True,
		"UseMaterialAppearance:=", False,
		"IsLightweight:="	, False
	])
oEditor = oDesign.SetActiveEditor("3D Modeler")
oEditor.ChangeProperty(
	[
		"NAME:AllTabs",
		[
			"NAME:Geometry3DCmdTab",
			[
				"NAME:PropServers", 
				"Rectangle1:CreateRectangle:1"
			],
			[
				"NAME:ChangedProps",
				[
					"NAME:Position",
					"X:="			, "30mm",
					"Y:="			, "0mm",
					"Z:="			, "0mm"
				],
				[
					"NAME:XSize",
					"Value:="		, "3mm"
				],
				[
					"NAME:ZSize",
					"Value:="		, "0.5mm"
				]
			]
		]
	])
oEditor = oDesign.SetActiveEditor("3D Modeler")
oEditor.CreatePolyline(
	[
		"NAME:PolylineParameters",
		"IsPolylineCovered:="	, True,
		"IsPolylineClosed:="	, False,
		[
			"NAME:PolylinePoints",
			[
				"NAME:PLPoint",
				"X:="			, "30mm",
				"Y:="			, "0mm",
				"Z:="			, "0mm"
			],
			[
				"NAME:PLPoint",
				"X:="			, "30mm",
				"Y:="			, "30mm",
				"Z:="			, "0mm"
			],
			[
				"NAME:PLPoint",
				"X:="			, "-30mm",
				"Y:="			, "30mm",
				"Z:="			, "0mm"
			],
			[
				"NAME:PLPoint",
				"X:="			, "-30mm",
				"Y:="			, "-30mm",
				"Z:="			, "0mm"
			],
			[
				"NAME:PLPoint",
				"X:="			, "34.5mm",
				"Y:="			, "-30mm",
				"Z:="			, "0mm"
			],
			[
				"NAME:PLPoint",
				"X:="			, "34.5mm",
				"Y:="			, "34.5mm",
				"Z:="			, "0mm"
			],
			[
				"NAME:PLPoint",
				"X:="			, "-34.5mm",
				"Y:="			, "34.5mm",
				"Z:="			, "0mm"
			],
			[
				"NAME:PLPoint",
				"X:="			, "-34.5mm",
				"Y:="			, "-34.5mm",
				"Z:="			, "0mm"
			],
			[
				"NAME:PLPoint",
				"X:="			, "39mm",
				"Y:="			, "-34.5mm",
				"Z:="			, "0mm"
			],
			[
				"NAME:PLPoint",
				"X:="			, "39mm",
				"Y:="			, "39mm",
				"Z:="			, "0mm"
			],
			[
				"NAME:PLPoint",
				"X:="			, "-39mm",
				"Y:="			, "39mm",
				"Z:="			, "0mm"
			],
			[
				"NAME:PLPoint",
				"X:="			, "-39mm",
				"Y:="			, "-39mm",
				"Z:="			, "0mm"
			],
			[
				"NAME:PLPoint",
				"X:="			, "43.5mm",
				"Y:="			, "-39mm",
				"Z:="			, "0mm"
			],
			[
				"NAME:PLPoint",
				"X:="			, "43.5mm",
				"Y:="			, "43.5mm",
				"Z:="			, "0mm"
			],
			[
				"NAME:PLPoint",
				"X:="			, "-43.5mm",
				"Y:="			, "43.5mm",
				"Z:="			, "0mm"
			],
			[
				"NAME:PLPoint",
				"X:="			, "-43.5mm",
				"Y:="			, "-43.5mm",
				"Z:="			, "0mm"
			],
			[
				"NAME:PLPoint",
				"X:="			, "48mm",
				"Y:="			, "-43.5mm",
				"Z:="			, "0mm"
			],
			[
				"NAME:PLPoint",
				"X:="			, "48mm",
				"Y:="			, "48mm",
				"Z:="			, "0mm"
			],
			[
				"NAME:PLPoint",
				"X:="			, "-48mm",
				"Y:="			, "48mm",
				"Z:="			, "0mm"
			],
			[
				"NAME:PLPoint",
				"X:="			, "-48mm",
				"Y:="			, "-48mm",
				"Z:="			, "0mm"
			],
			[
				"NAME:PLPoint",
				"X:="			, "52.5mm",
				"Y:="			, "-48mm",
				"Z:="			, "0mm"
			],
			[
				"NAME:PLPoint",
				"X:="			, "52.5mm",
				"Y:="			, "52.5mm",
				"Z:="			, "0mm"
			],
			[
				"NAME:PLPoint",
				"X:="			, "-52.5mm",
				"Y:="			, "52.5mm",
				"Z:="			, "0mm"
			],
			[
				"NAME:PLPoint",
				"X:="			, "-52.5mm",
				"Y:="			, "-52.5mm",
				"Z:="			, "0mm"
			],
			[
				"NAME:PLPoint",
				"X:="			, "57mm",
				"Y:="			, "-52.5mm",
				"Z:="			, "0mm"
			],
			[
				"NAME:PLPoint",
				"X:="			, "57mm",
				"Y:="			, "57mm",
				"Z:="			, "0mm"
			],
			[
				"NAME:PLPoint",
				"X:="			, "-57mm",
				"Y:="			, "57mm",
				"Z:="			, "0mm"
			],
			[
				"NAME:PLPoint",
				"X:="			, "-57mm",
				"Y:="			, "-57mm",
				"Z:="			, "0mm"
			],
			[
				"NAME:PLPoint",
				"X:="			, "61.5mm",
				"Y:="			, "-57mm",
				"Z:="			, "0mm"
			],
			[
				"NAME:PLPoint",
				"X:="			, "61.5mm",
				"Y:="			, "61.5mm",
				"Z:="			, "0mm"
			],
			[
				"NAME:PLPoint",
				"X:="			, "-61.5mm",
				"Y:="			, "61.5mm",
				"Z:="			, "0mm"
			],
			[
				"NAME:PLPoint",
				"X:="			, "-61.5mm",
				"Y:="			, "-61.5mm",
				"Z:="			, "0mm"
			],
			[
				"NAME:PLPoint",
				"X:="			, "66mm",
				"Y:="			, "-61.5mm",
				"Z:="			, "0mm"
			],
			[
				"NAME:PLPoint",
				"X:="			, "66mm",
				"Y:="			, "66mm",
				"Z:="			, "0mm"
			],
			[
				"NAME:PLPoint",
				"X:="			, "-66mm",
				"Y:="			, "66mm",
				"Z:="			, "0mm"
			],
			[
				"NAME:PLPoint",
				"X:="			, "-66mm",
				"Y:="			, "-66mm",
				"Z:="			, "0mm"
			],
			[
				"NAME:PLPoint",
				"X:="			, "70.5mm",
				"Y:="			, "-66mm",
				"Z:="			, "0mm"
			],
			[
				"NAME:PLPoint",
				"X:="			, "70.5mm",
				"Y:="			, "70.5mm",
				"Z:="			, "0mm"
			],
			[
				"NAME:PLPoint",
				"X:="			, "-70.5mm",
				"Y:="			, "70.5mm",
				"Z:="			, "0mm"
			],
			[
				"NAME:PLPoint",
				"X:="			, "-70.5mm",
				"Y:="			, "-70.5mm",
				"Z:="			, "0mm"
			],
			[
				"NAME:PLPoint",
				"X:="			, "75mm",
				"Y:="			, "-70.5mm",
				"Z:="			, "0mm"
			],
			[
				"NAME:PLPoint",
				"X:="			, "75mm",
				"Y:="			, "75mm",
				"Z:="			, "0mm"
			],
			[
				"NAME:PLPoint",
				"X:="			, "-75mm",
				"Y:="			, "75mm",
				"Z:="			, "0mm"
			],
			[
				"NAME:PLPoint",
				"X:="			, "-75mm",
				"Y:="			, "-75mm",
				"Z:="			, "0mm"
			],
			[
				"NAME:PLPoint",
				"X:="			, "79.5mm",
				"Y:="			, "-75mm",
				"Z:="			, "0mm"
			],
			[
				"NAME:PLPoint",
				"X:="			, "79.5mm",
				"Y:="			, "79.5mm",
				"Z:="			, "0mm"
			],
			[
				"NAME:PLPoint",
				"X:="			, "-79.5mm",
				"Y:="			, "79.5mm",
				"Z:="			, "0mm"
			],
			[
				"NAME:PLPoint",
				"X:="			, "-79.5mm",
				"Y:="			, "-79.5mm",
				"Z:="			, "0mm"
			],
			[
				"NAME:PLPoint",
				"X:="			, "84mm",
				"Y:="			, "-79.5mm",
				"Z:="			, "0mm"
			],
			[
				"NAME:PLPoint",
				"X:="			, "84mm",
				"Y:="			, "0mm",
				"Z:="			, "0mm"
			]
		],
		[
			"NAME:PolylineSegments",
			[
				"NAME:PLSegment",
				"SegmentType:="		, "Line",
				"StartIndex:="		, 0,
				"NoOfPoints:="		, 2
			],
			[
				"NAME:PLSegment",
				"SegmentType:="		, "Line",
				"StartIndex:="		, 1,
				"NoOfPoints:="		, 2
			],
			[
				"NAME:PLSegment",
				"SegmentType:="		, "Line",
				"StartIndex:="		, 2,
				"NoOfPoints:="		, 2
			],
			[
				"NAME:PLSegment",
				"SegmentType:="		, "Line",
				"StartIndex:="		, 3,
				"NoOfPoints:="		, 2
			],
			[
				"NAME:PLSegment",
				"SegmentType:="		, "Line",
				"StartIndex:="		, 4,
				"NoOfPoints:="		, 2
			],
			[
				"NAME:PLSegment",
				"SegmentType:="		, "Line",
				"StartIndex:="		, 5,
				"NoOfPoints:="		, 2
			],
			[
				"NAME:PLSegment",
				"SegmentType:="		, "Line",
				"StartIndex:="		, 6,
				"NoOfPoints:="		, 2
			],
			[
				"NAME:PLSegment",
				"SegmentType:="		, "Line",
				"StartIndex:="		, 7,
				"NoOfPoints:="		, 2
			],
			[
				"NAME:PLSegment",
				"SegmentType:="		, "Line",
				"StartIndex:="		, 8,
				"NoOfPoints:="		, 2
			],
			[
				"NAME:PLSegment",
				"SegmentType:="		, "Line",
				"StartIndex:="		, 9,
				"NoOfPoints:="		, 2
			],
			[
				"NAME:PLSegment",
				"SegmentType:="		, "Line",
				"StartIndex:="		, 10,
				"NoOfPoints:="		, 2
			],
			[
				"NAME:PLSegment",
				"SegmentType:="		, "Line",
				"StartIndex:="		, 11,
				"NoOfPoints:="		, 2
			],
			[
				"NAME:PLSegment",
				"SegmentType:="		, "Line",
				"StartIndex:="		, 12,
				"NoOfPoints:="		, 2
			],
			[
				"NAME:PLSegment",
				"SegmentType:="		, "Line",
				"StartIndex:="		, 13,
				"NoOfPoints:="		, 2
			],
			[
				"NAME:PLSegment",
				"SegmentType:="		, "Line",
				"StartIndex:="		, 14,
				"NoOfPoints:="		, 2
			],
			[
				"NAME:PLSegment",
				"SegmentType:="		, "Line",
				"StartIndex:="		, 15,
				"NoOfPoints:="		, 2
			],
			[
				"NAME:PLSegment",
				"SegmentType:="		, "Line",
				"StartIndex:="		, 16,
				"NoOfPoints:="		, 2
			],
			[
				"NAME:PLSegment",
				"SegmentType:="		, "Line",
				"StartIndex:="		, 17,
				"NoOfPoints:="		, 2
			],
			[
				"NAME:PLSegment",
				"SegmentType:="		, "Line",
				"StartIndex:="		, 18,
				"NoOfPoints:="		, 2
			],
			[
				"NAME:PLSegment",
				"SegmentType:="		, "Line",
				"StartIndex:="		, 19,
				"NoOfPoints:="		, 2
			],
			[
				"NAME:PLSegment",
				"SegmentType:="		, "Line",
				"StartIndex:="		, 20,
				"NoOfPoints:="		, 2
			],
			[
				"NAME:PLSegment",
				"SegmentType:="		, "Line",
				"StartIndex:="		, 21,
				"NoOfPoints:="		, 2
			],
			[
				"NAME:PLSegment",
				"SegmentType:="		, "Line",
				"StartIndex:="		, 22,
				"NoOfPoints:="		, 2
			],
			[
				"NAME:PLSegment",
				"SegmentType:="		, "Line",
				"StartIndex:="		, 23,
				"NoOfPoints:="		, 2
			],
			[
				"NAME:PLSegment",
				"SegmentType:="		, "Line",
				"StartIndex:="		, 24,
				"NoOfPoints:="		, 2
			],
			[
				"NAME:PLSegment",
				"SegmentType:="		, "Line",
				"StartIndex:="		, 25,
				"NoOfPoints:="		, 2
			],
			[
				"NAME:PLSegment",
				"SegmentType:="		, "Line",
				"StartIndex:="		, 26,
				"NoOfPoints:="		, 2
			],
			[
				"NAME:PLSegment",
				"SegmentType:="		, "Line",
				"StartIndex:="		, 27,
				"NoOfPoints:="		, 2
			],
			[
				"NAME:PLSegment",
				"SegmentType:="		, "Line",
				"StartIndex:="		, 28,
				"NoOfPoints:="		, 2
			],
			[
				"NAME:PLSegment",
				"SegmentType:="		, "Line",
				"StartIndex:="		, 29,
				"NoOfPoints:="		, 2
			],
			[
				"NAME:PLSegment",
				"SegmentType:="		, "Line",
				"StartIndex:="		, 30,
				"NoOfPoints:="		, 2
			],
			[
				"NAME:PLSegment",
				"SegmentType:="		, "Line",
				"StartIndex:="		, 31,
				"NoOfPoints:="		, 2
			],
			[
				"NAME:PLSegment",
				"SegmentType:="		, "Line",
				"StartIndex:="		, 32,
				"NoOfPoints:="		, 2
			],
			[
				"NAME:PLSegment",
				"SegmentType:="		, "Line",
				"StartIndex:="		, 33,
				"NoOfPoints:="		, 2
			],
			[
				"NAME:PLSegment",
				"SegmentType:="		, "Line",
				"StartIndex:="		, 34,
				"NoOfPoints:="		, 2
			],
			[
				"NAME:PLSegment",
				"SegmentType:="		, "Line",
				"StartIndex:="		, 35,
				"NoOfPoints:="		, 2
			],
			[
				"NAME:PLSegment",
				"SegmentType:="		, "Line",
				"StartIndex:="		, 36,
				"NoOfPoints:="		, 2
			],
			[
				"NAME:PLSegment",
				"SegmentType:="		, "Line",
				"StartIndex:="		, 37,
				"NoOfPoints:="		, 2
			],
			[
				"NAME:PLSegment",
				"SegmentType:="		, "Line",
				"StartIndex:="		, 38,
				"NoOfPoints:="		, 2
			],
			[
				"NAME:PLSegment",
				"SegmentType:="		, "Line",
				"StartIndex:="		, 39,
				"NoOfPoints:="		, 2
			],
			[
				"NAME:PLSegment",
				"SegmentType:="		, "Line",
				"StartIndex:="		, 40,
				"NoOfPoints:="		, 2
			],
			[
				"NAME:PLSegment",
				"SegmentType:="		, "Line",
				"StartIndex:="		, 41,
				"NoOfPoints:="		, 2
			],
			[
				"NAME:PLSegment",
				"SegmentType:="		, "Line",
				"StartIndex:="		, 42,
				"NoOfPoints:="		, 2
			],
			[
				"NAME:PLSegment",
				"SegmentType:="		, "Line",
				"StartIndex:="		, 43,
				"NoOfPoints:="		, 2
			],
			[
				"NAME:PLSegment",
				"SegmentType:="		, "Line",
				"StartIndex:="		, 44,
				"NoOfPoints:="		, 2
			],
			[
				"NAME:PLSegment",
				"SegmentType:="		, "Line",
				"StartIndex:="		, 45,
				"NoOfPoints:="		, 2
			],
			[
				"NAME:PLSegment",
				"SegmentType:="		, "Line",
				"StartIndex:="		, 46,
				"NoOfPoints:="		, 2
			],
			[
				"NAME:PLSegment",
				"SegmentType:="		, "Line",
				"StartIndex:="		, 47,
				"NoOfPoints:="		, 2
			],
			[
				"NAME:PLSegment",
				"SegmentType:="		, "Line",
				"StartIndex:="		, 48,
				"NoOfPoints:="		, 2
			]
		],
		[
			"NAME:PolylineXSection",
			"XSectionType:="	, "None",
			"XSectionOrient:="	, "Auto",
			"XSectionWidth:="	, "0mm",
			"XSectionTopWidth:="	, "0mm",
			"XSectionHeight:="	, "0mm",
			"XSectionNumSegments:="	, "0",
			"XSectionBendType:="	, "Corner"
		]
	], 
	[
		"NAME:Attributes",
		"Name:="		, "Polyline1",
		"Flags:="		, "",
		"Color:="		, "(143 175 143)",
		"Transparency:="	, 0,
		"PartCoordinateSystem:=", "Global",
		"UDMId:="		, "",
		"MaterialValue:="	, "\"vacuum\"",
		"SurfaceMaterialValue:=", "\"\"",
		"SolveInside:="		, True,
		"ShellElement:="	, False,
		"ShellElementThickness:=", "0mm",
		"ReferenceTemperature:=", "20cel",
		"IsMaterialEditable:="	, True,
		"UseMaterialAppearance:=", False,
		"IsLightweight:="	, False
	])
oEditor.Fillet(
	[
		"NAME:Selections",
		"Selections:="		, "Polyline1",
		"NewPartsModelFlag:="	, "Model"
	], 
	[
		"NAME:Parameters",
		[
			"NAME:FilletParameters",
			"Edges:="		, [],
			"Vertices:="		, [70,69],
			"Radius:="		, "10mm",
			"Setback:="		, "0mm"
		]
	])
oEditor.Fillet(
	[
		"NAME:Selections",
		"Selections:="		, "Polyline1",
		"NewPartsModelFlag:="	, "Model"
	], 
	[
		"NAME:Parameters",
		[
			"NAME:FilletParameters",
			"Edges:="		, [],
			"Vertices:="		, [71],
			"Radius:="		, "10mm",
			"Setback:="		, "0mm"
		]
	])
oEditor.Fillet(
	[
		"NAME:Selections",
		"Selections:="		, "Polyline1",
		"NewPartsModelFlag:="	, "Model"
	], 
	[
		"NAME:Parameters",
		[
			"NAME:FilletParameters",
			"Edges:="		, [],
			"Vertices:="		, [72],
			"Radius:="		, "10mm",
			"Setback:="		, "0mm"
		]
	])
oEditor.Fillet(
	[
		"NAME:Selections",
		"Selections:="		, "Polyline1",
		"NewPartsModelFlag:="	, "Model"
	], 
	[
		"NAME:Parameters",
		[
			"NAME:FilletParameters",
			"Edges:="		, [],
			"Vertices:="		, [74,73,75,76],
			"Radius:="		, "14.5mm",
			"Setback:="		, "0mm"
		]
	])
oEditor.Fillet(
	[
		"NAME:Selections",
		"Selections:="		, "Polyline1",
		"NewPartsModelFlag:="	, "Model"
	], 
	[
		"NAME:Parameters",
		[
			"NAME:FilletParameters",
			"Edges:="		, [],
			"Vertices:="		, [78,77,80,79],
			"Radius:="		, "19mm",
			"Setback:="		, "0mm"
		]
	])
oEditor.Fillet(
	[
		"NAME:Selections",
		"Selections:="		, "Polyline1",
		"NewPartsModelFlag:="	, "Model"
	], 
	[
		"NAME:Parameters",
		[
			"NAME:FilletParameters",
			"Edges:="		, [],
			"Vertices:="		, [84,81,82,83],
			"Radius:="		, "23.5mm",
			"Setback:="		, "0mm"
		]
	])
oEditor.Fillet(
	[
		"NAME:Selections",
		"Selections:="		, "Polyline1",
		"NewPartsModelFlag:="	, "Model"
	], 
	[
		"NAME:Parameters",
		[
			"NAME:FilletParameters",
			"Edges:="		, [],
			"Vertices:="		, [86,85,88,87],
			"Radius:="		, "28mm",
			"Setback:="		, "0mm"
		]
	])
oEditor.Fillet(
	[
		"NAME:Selections",
		"Selections:="		, "Polyline1",
		"NewPartsModelFlag:="	, "Model"
	], 
	[
		"NAME:Parameters",
		[
			"NAME:FilletParameters",
			"Edges:="		, [],
			"Vertices:="		, [91,90,89,92],
			"Radius:="		, "32.5mm",
			"Setback:="		, "0mm"
		]
	])
oEditor.Fillet(
	[
		"NAME:Selections",
		"Selections:="		, "Polyline1",
		"NewPartsModelFlag:="	, "Model"
	], 
	[
		"NAME:Parameters",
		[
			"NAME:FilletParameters",
			"Edges:="		, [],
			"Vertices:="		, [94,93,96,95],
			"Radius:="		, "37mm",
			"Setback:="		, "0mm"
		]
	])
oEditor.Fillet(
	[
		"NAME:Selections",
		"Selections:="		, "Polyline1",
		"NewPartsModelFlag:="	, "Model"
	], 
	[
		"NAME:Parameters",
		[
			"NAME:FilletParameters",
			"Edges:="		, [],
			"Vertices:="		, [97,100,99,98],
			"Radius:="		, "41.5mm",
			"Setback:="		, "0mm"
		]
	])
oEditor.Fillet(
	[
		"NAME:Selections",
		"Selections:="		, "Polyline1",
		"NewPartsModelFlag:="	, "Model"
	], 
	[
		"NAME:Parameters",
		[
			"NAME:FilletParameters",
			"Edges:="		, [],
			"Vertices:="		, [102,101,104,103],
			"Radius:="		, "46mm",
			"Setback:="		, "0mm"
		]
	])
oEditor.Fillet(
	[
		"NAME:Selections",
		"Selections:="		, "Polyline1",
		"NewPartsModelFlag:="	, "Model"
	], 
	[
		"NAME:Parameters",
		[
			"NAME:FilletParameters",
			"Edges:="		, [],
			"Vertices:="		, [106,105,108,107],
			"Radius:="		, "50.5mm",
			"Setback:="		, "0mm"
		]
	])
oEditor.Fillet(
	[
		"NAME:Selections",
		"Selections:="		, "Polyline1",
		"NewPartsModelFlag:="	, "Model"
	], 
	[
		"NAME:Parameters",
		[
			"NAME:FilletParameters",
			"Edges:="		, [],
			"Vertices:="		, [110,109,112,111],
			"Radius:="		, "55mm",
			"Setback:="		, "0mm"
		]
	])
oEditor.Fillet(
	[
		"NAME:Selections",
		"Selections:="		, "Polyline1",
		"NewPartsModelFlag:="	, "Model"
	], 
	[
		"NAME:Parameters",
		[
			"NAME:FilletParameters",
			"Edges:="		, [],
			"Vertices:="		, [114,113,116,115],
			"Radius:="		, "59.5mm",
			"Setback:="		, "0mm"
		]
	])
oEditor.SweepAlongPath(
	[
		"NAME:Selections",
		"Selections:="		, "Polyline1,Rectangle1",
		"NewPartsModelFlag:="	, "Model"
	], 
	[
		"NAME:PathSweepParameters",
		"DraftAngle:="		, "0deg",
		"DraftType:="		, "Round",
		"CheckFaceFaceIntersection:=", False,
		"ClearAllIDs:="		, False,
		"TwistAngle:="		, "0deg"
	])
oEditor.CreatePolyline(
	[
		"NAME:PolylineParameters",
		"IsPolylineCovered:="	, True,
		"IsPolylineClosed:="	, False,
		[
			"NAME:PolylinePoints",
			[
				"NAME:PLPoint",
				"X:="			, "31.5mm",
				"Y:="			, "0mm",
				"Z:="			, "0.25mm"
			],
			[
				"NAME:PLPoint",
				"X:="			, "31.5mm",
				"Y:="			, "8.5mm",
				"Z:="			, "0mm"
			],
			[
				"NAME:PLPoint",
				"X:="			, "85mm",
				"Y:="			, "11mm",
				"Z:="			, "0mm"
			],
			[
				"NAME:PLPoint",
				"X:="			, "85.5mm",
				"Y:="			, "0mm",
				"Z:="			, "0.25mm"
			],
			[
				"NAME:PLPoint",
				"X:="			, "85.5mm",
				"Y:="			, "0mm",
				"Z:="			, "0.5mm"
			]
		],
		[
			"NAME:PolylineSegments",
			[
				"NAME:PLSegment",
				"SegmentType:="		, "Line",
				"StartIndex:="		, 0,
				"NoOfPoints:="		, 2
			],
			[
				"NAME:PLSegment",
				"SegmentType:="		, "Line",
				"StartIndex:="		, 1,
				"NoOfPoints:="		, 2
			],
			[
				"NAME:PLSegment",
				"SegmentType:="		, "Line",
				"StartIndex:="		, 2,
				"NoOfPoints:="		, 2
			],
			[
				"NAME:PLSegment",
				"SegmentType:="		, "Line",
				"StartIndex:="		, 3,
				"NoOfPoints:="		, 2
			]
		],
		[
			"NAME:PolylineXSection",
			"XSectionType:="	, "None",
			"XSectionOrient:="	, "Auto",
			"XSectionWidth:="	, "0mm",
			"XSectionTopWidth:="	, "0mm",
			"XSectionHeight:="	, "0mm",
			"XSectionNumSegments:="	, "0",
			"XSectionBendType:="	, "Corner"
		]
	], 
	[
		"NAME:Attributes",
		"Name:="		, "Polyline2",
		"Flags:="		, "",
		"Color:="		, "(143 175 143)",
		"Transparency:="	, 0,
		"PartCoordinateSystem:=", "Global",
		"UDMId:="		, "",
		"MaterialValue:="	, "\"vacuum\"",
		"SurfaceMaterialValue:=", "\"\"",
		"SolveInside:="		, True,
		"ShellElement:="	, False,
		"ShellElementThickness:=", "0mm",
		"ReferenceTemperature:=", "20cel",
		"IsMaterialEditable:="	, True,
		"UseMaterialAppearance:=", False,
		"IsLightweight:="	, False
	])
oEditor.Delete(
	[
		"NAME:Selections",
		"Selections:="		, "Polyline2"
	])
oEditor.CreatePolyline(
	[
		"NAME:PolylineParameters",
		"IsPolylineCovered:="	, True,
		"IsPolylineClosed:="	, False,
		[
			"NAME:PolylinePoints",
			[
				"NAME:PLPoint",
				"X:="			, "31.5mm",
				"Y:="			, "0mm",
				"Z:="			, "0.25mm"
			],
			[
				"NAME:PLPoint",
				"X:="			, "32mm",
				"Y:="			, "20mm",
				"Z:="			, "0mm"
			],
			[
				"NAME:PLPoint",
				"X:="			, "86mm",
				"Y:="			, "20mm",
				"Z:="			, "0mm"
			],
			[
				"NAME:PLPoint",
				"X:="			, "85.5mm",
				"Y:="			, "0.5mm",
				"Z:="			, "0mm"
			]
		],
		[
			"NAME:PolylineSegments",
			[
				"NAME:PLSegment",
				"SegmentType:="		, "Line",
				"StartIndex:="		, 0,
				"NoOfPoints:="		, 2
			],
			[
				"NAME:PLSegment",
				"SegmentType:="		, "Line",
				"StartIndex:="		, 1,
				"NoOfPoints:="		, 2
			],
			[
				"NAME:PLSegment",
				"SegmentType:="		, "Line",
				"StartIndex:="		, 2,
				"NoOfPoints:="		, 2
			]
		],
		[
			"NAME:PolylineXSection",
			"XSectionType:="	, "None",
			"XSectionOrient:="	, "Auto",
			"XSectionWidth:="	, "0mm",
			"XSectionTopWidth:="	, "0mm",
			"XSectionHeight:="	, "0mm",
			"XSectionNumSegments:="	, "0",
			"XSectionBendType:="	, "Corner"
		]
	], 
	[
		"NAME:Attributes",
		"Name:="		, "Polyline2",
		"Flags:="		, "",
		"Color:="		, "(143 175 143)",
		"Transparency:="	, 0,
		"PartCoordinateSystem:=", "Global",
		"UDMId:="		, "",
		"MaterialValue:="	, "\"vacuum\"",
		"SurfaceMaterialValue:=", "\"\"",
		"SolveInside:="		, True,
		"ShellElement:="	, False,
		"ShellElementThickness:=", "0mm",
		"ReferenceTemperature:=", "20cel",
		"IsMaterialEditable:="	, True,
		"UseMaterialAppearance:=", False,
		"IsLightweight:="	, False
	])
oDesign.Undo()
oEditor.CreatePolyline(
	[
		"NAME:PolylineParameters",
		"IsPolylineCovered:="	, True,
		"IsPolylineClosed:="	, False,
		[
			"NAME:PolylinePoints",
			[
				"NAME:PLPoint",
				"X:="			, "31.5mm",
				"Y:="			, "0mm",
				"Z:="			, "0.25mm"
			],
			[
				"NAME:PLPoint",
				"X:="			, "32mm",
				"Y:="			, "19mm",
				"Z:="			, "0mm"
			],
			[
				"NAME:PLPoint",
				"X:="			, "85mm",
				"Y:="			, "25mm",
				"Z:="			, "0mm"
			],
			[
				"NAME:PLPoint",
				"X:="			, "85.5mm",
				"Y:="			, "0mm",
				"Z:="			, "0.25mm"
			]
		],
		[
			"NAME:PolylineSegments",
			[
				"NAME:PLSegment",
				"SegmentType:="		, "Line",
				"StartIndex:="		, 0,
				"NoOfPoints:="		, 2
			],
			[
				"NAME:PLSegment",
				"SegmentType:="		, "Line",
				"StartIndex:="		, 1,
				"NoOfPoints:="		, 2
			],
			[
				"NAME:PLSegment",
				"SegmentType:="		, "Line",
				"StartIndex:="		, 2,
				"NoOfPoints:="		, 2
			]
		],
		[
			"NAME:PolylineXSection",
			"XSectionType:="	, "None",
			"XSectionOrient:="	, "Auto",
			"XSectionWidth:="	, "0mm",
			"XSectionTopWidth:="	, "0mm",
			"XSectionHeight:="	, "0mm",
			"XSectionNumSegments:="	, "0",
			"XSectionBendType:="	, "Corner"
		]
	], 
	[
		"NAME:Attributes",
		"Name:="		, "Polyline2",
		"Flags:="		, "",
		"Color:="		, "(143 175 143)",
		"Transparency:="	, 0,
		"PartCoordinateSystem:=", "Global",
		"UDMId:="		, "",
		"MaterialValue:="	, "\"vacuum\"",
		"SurfaceMaterialValue:=", "\"\"",
		"SolveInside:="		, True,
		"ShellElement:="	, False,
		"ShellElementThickness:=", "0mm",
		"ReferenceTemperature:=", "20cel",
		"IsMaterialEditable:="	, True,
		"UseMaterialAppearance:=", False,
		"IsLightweight:="	, False
	])
oEditor = oDesign.SetActiveEditor("3D Modeler")
oEditor.ChangeProperty(
	[
		"NAME:AllTabs",
		[
			"NAME:Geometry3DPolylineTab",
			[
				"NAME:PropServers", 
				"Polyline2:CreatePolyline:1:Segment0"
			],
			[
				"NAME:ChangedProps",
				[
					"NAME:Point1",
					"X:="			, "31.5mm",
					"Y:="			, "0mm",
					"Z:="			, "0mm"
				],
				[
					"NAME:Point2",
					"X:="			, "31.5mm",
					"Y:="			, "0mm",
					"Z:="			, "3mm"
				]
			]
		]
	])
oEditor.ChangeProperty(
	[
		"NAME:AllTabs",
		[
			"NAME:Geometry3DPolylineTab",
			[
				"NAME:PropServers", 
				"Polyline2:CreatePolyline:1:Segment2"
			],
			[
				"NAME:ChangedProps",
				[
					"NAME:Point2",
					"X:="			, "85.5mm",
					"Y:="			, "0mm",
					"Z:="			, "0mm"
				],
				[
					"NAME:Point1",
					"X:="			, "85.5mm",
					"Y:="			, "0mm",
					"Z:="			, "3mm"
				]
			]
		]
	])
oEditor.ChangeProperty(
	[
		"NAME:AllTabs",
		[
			"NAME:Geometry3DCmdTab",
			[
				"NAME:PropServers", 
				"Polyline2:CreatePolyline:1"
			],
			[
				"NAME:ChangedProps",
				[
					"NAME:Type",
					"Value:="		, "Rectangle"
				],
				[
					"NAME:Width/Diameter",
					"Value:="		, "3mm"
				],
				[
					"NAME:Height",
					"Value:="		, "0.5mm"
				]
			]
		]
	])
oEditor = oDesign.SetActiveEditor("3D Modeler")
oEditor.Unite(
	[
		"NAME:Selections",
		"Selections:="		, "Polyline2,Rectangle1"
	], 
	[
		"NAME:UniteParameters",
		"KeepOriginals:="	, False,
		"TurnOnNBodyBoolean:="	, True
	])
oEditor = oDesign.SetActiveEditor("3D Modeler")
oEditor.ChangeProperty(
	[
		"NAME:AllTabs",
		[
			"NAME:Geometry3DAttributeTab",
			[
				"NAME:PropServers", 
				"Polyline2"
			],
			[
				"NAME:ChangedProps",
				[
					"NAME:Name",
					"Value:="		, "coil_1"
				]
			]
		]
	])
oEditor = oDesign.SetActiveEditor("3D Modeler")
oEditor.AssignMaterial(
	[
		"NAME:Selections",
		"AllowRegionDependentPartSelectionForPMLCreation:=", True,
		"AllowRegionSelectionForPMLCreation:=", True,
		"Selections:="		, "coil_1"
	], 
	[
		"NAME:Attributes",
		"MaterialValue:="	, "\"copper\"",
		"SolveInside:="		, True,
		"ShellElement:="	, False,
		"ShellElementThickness:=", "nan ",
		"ReferenceTemperature:=", "nan ",
		"IsMaterialEditable:="	, True,
		"UseMaterialAppearance:=", False,
		"IsLightweight:="	, False
	])
oEditor = oDesign.SetActiveEditor("3D Modeler")
oEditor.DuplicateMirror(
	[
		"NAME:Selections",
		"Selections:="		, "coil_1",
		"NewPartsModelFlag:="	, "Model"
	], 
	[
		"NAME:DuplicateToMirrorParameters",
		"DuplicateMirrorBaseX:=", "0mm",
		"DuplicateMirrorBaseY:=", "0mm",
		"DuplicateMirrorBaseZ:=", "0mm",
		"DuplicateMirrorNormalX:=", "0mm",
		"DuplicateMirrorNormalY:=", "0mm",
		"DuplicateMirrorNormalZ:=", "-1mm"
	], 
	[
		"NAME:Options",
		"DuplicateAssignments:=", True
	], 
	[
		"CreateGroupsForNewObjects:=", False
	])
oEditor = oDesign.SetActiveEditor("3D Modeler")
oEditor.ChangeProperty(
	[
		"NAME:AllTabs",
		[
			"NAME:Geometry3DAttributeTab",
			[
				"NAME:PropServers", 
				"coil_1_1"
			],
			[
				"NAME:ChangedProps",
				[
					"NAME:Name",
					"Value:="		, "coil_2"
				]
			]
		]
	])
oEditor = oDesign.SetActiveEditor("3D Modeler")
oEditor.DuplicateMirror(
	[
		"NAME:Selections",
		"Selections:="		, "coil_1",
		"NewPartsModelFlag:="	, "Model"
	], 
	[
		"NAME:DuplicateToMirrorParameters",
		"DuplicateMirrorBaseX:=", "0mm",
		"DuplicateMirrorBaseY:=", "-100mm",
		"DuplicateMirrorBaseZ:=", "0mm",
		"DuplicateMirrorNormalX:=", "-0.894427190999916mm",
		"DuplicateMirrorNormalY:=", "-0.447213595499958mm",
		"DuplicateMirrorNormalZ:=", "0mm"
	], 
	[
		"NAME:Options",
		"DuplicateAssignments:=", True
	], 
	[
		"CreateGroupsForNewObjects:=", False
	])
oDesign.Undo()
oEditor.DuplicateAlongLine(
	[
		"NAME:Selections",
		"Selections:="		, "coil_1",
		"NewPartsModelFlag:="	, "Model"
	], 
	[
		"NAME:DuplicateToAlongLineParameters",
		"CreateNewObjects:="	, True,
		"XComponent:="		, "-11mm",
		"YComponent:="		, "-13mm",
		"ZComponent:="		, "0mm",
		"NumClones:="		, "2"
	], 
	[
		"NAME:Options",
		"DuplicateAssignments:=", True
	], 
	[
		"CreateGroupsForNewObjects:=", False
	])
oDesign.Undo()
oEditor.DuplicateAlongLine(
	[
		"NAME:Selections",
		"Selections:="		, "coil_1",
		"NewPartsModelFlag:="	, "Model"
	], 
	[
		"NAME:DuplicateToAlongLineParameters",
		"CreateNewObjects:="	, True,
		"XComponent:="		, "0mm",
		"YComponent:="		, "0mm",
		"ZComponent:="		, "10mm",
		"NumClones:="		, "2"
	], 
	[
		"NAME:Options",
		"DuplicateAssignments:=", True
	], 
	[
		"CreateGroupsForNewObjects:=", False
	])
oEditor = oDesign.SetActiveEditor("3D Modeler")
oEditor.ChangeProperty(
	[
		"NAME:AllTabs",
		[
			"NAME:Geometry3DAttributeTab",
			[
				"NAME:PropServers", 
				"coil_1_1"
			],
			[
				"NAME:ChangedProps",
				[
					"NAME:Name",
					"Value:="		, "coil_3"
				]
			]
		]
	])
oEditor.ChangeProperty(
	[
		"NAME:AllTabs",
		[
			"NAME:Geometry3DAttributeTab",
			[
				"NAME:PropServers", 
				"coil_3"
			],
			[
				"NAME:ChangedProps",
				[
					"NAME:Color",
					"R:="			, 255,
					"G:="			, 128,
					"B:="			, 128
				]
			]
		]
	])
oEditor.ChangeProperty(
	[
		"NAME:AllTabs",
		[
			"NAME:Geometry3DAttributeTab",
			[
				"NAME:PropServers", 
				"coil_2"
			],
			[
				"NAME:ChangedProps",
				[
					"NAME:Color",
					"R:="			, 133,
					"G:="			, 165,
					"B:="			, 250
				]
			]
		]
	])
oEditor = oDesign.SetActiveEditor("3D Modeler")
oEditor.Section(
	[
		"NAME:Selections",
		"Selections:="		, "coil_3",
		"NewPartsModelFlag:="	, "Model"
	], 
	[
		"NAME:SectionToParameters",
		"CreateNewObjects:="	, True,
		"SectionPlane:="	, "YZ",
		"SectionCrossObject:="	, False
	])
oEditor.SeparateBody(
	[
		"NAME:Selections",
		"Selections:="		, "coil_3_Section1",
		"NewPartsModelFlag:="	, "Model"
	], 
	[
		"CreateGroupsForNewObjects:=", False
	])
oEditor.Delete(
	[
		"NAME:Selections",
		"Selections:="		, "coil_3_Section1_Separate1,coil_3_Section1_Separate2,coil_3_Section1_Separate3,coil_3_Section1_Separate4,coil_3_Section1_Separate5,coil_3_Section1_Separate6,coil_3_Section1_Separate7,coil_3_Section1_Separate8,coil_3_Section1_Separate9,coil_3_Section1_Separate10,coil_3_Section1_Separate11,coil_3_Section1_Separate12,coil_3_Section1_Separate13,coil_3_Section1_Separate14,coil_3_Section1_Separate15,coil_3_Section1_Separate16,coil_3_Section1_Separate17,coil_3_Section1_Separate18,coil_3_Section1_Separate19,coil_3_Section1_Separate20,coil_3_Section1_Separate21,coil_3_Section1_Separate22,coil_3_Section1_Separate23"
	])
oModule = oDesign.GetModule("BoundarySetup")
oModule.AssignCurrent(
	[
		"NAME:Current3",
		"Objects:="		, ["coil_3_Section1"],
		"Current:="		, "1A",
		"IsSolid:="		, False,
		"Point out of terminal:=", False
	])
oEditor.Section(
	[
		"NAME:Selections",
		"Selections:="		, "coil_1",
		"NewPartsModelFlag:="	, "Model"
	], 
	[
		"NAME:SectionToParameters",
		"CreateNewObjects:="	, True,
		"SectionPlane:="	, "YZ",
		"SectionCrossObject:="	, False
	])
oEditor.SeparateBody(
	[
		"NAME:Selections",
		"Selections:="		, "coil_1_Section1",
		"NewPartsModelFlag:="	, "Model"
	], 
	[
		"CreateGroupsForNewObjects:=", False
	])
oEditor.Delete(
	[
		"NAME:Selections",
		"Selections:="		, "coil_1_Section1_Separate1,coil_1_Section1_Separate2,coil_1_Section1_Separate3,coil_1_Section1_Separate4,coil_1_Section1_Separate5,coil_1_Section1_Separate6,coil_1_Section1_Separate7,coil_1_Section1_Separate8,coil_1_Section1_Separate9,coil_1_Section1_Separate10,coil_1_Section1_Separate11,coil_1_Section1_Separate12,coil_1_Section1_Separate13,coil_1_Section1_Separate14,coil_1_Section1_Separate15,coil_1_Section1_Separate16,coil_1_Section1_Separate17,coil_1_Section1_Separate18,coil_1_Section1_Separate19,coil_1_Section1_Separate20,coil_1_Section1_Separate21,coil_1_Section1_Separate22,coil_1_Section1_Separate23"
	])
oModule.AssignCurrent(
	[
		"NAME:Current1",
		"Objects:="		, ["coil_1_Section1"],
		"Current:="		, "1A",
		"IsSolid:="		, False,
		"Point out of terminal:=", False
	])
oEditor.Section(
	[
		"NAME:Selections",
		"Selections:="		, "coil_2",
		"NewPartsModelFlag:="	, "Model"
	], 
	[
		"NAME:SectionToParameters",
		"CreateNewObjects:="	, True,
		"SectionPlane:="	, "YZ",
		"SectionCrossObject:="	, False
	])
oEditor.SeparateBody(
	[
		"NAME:Selections",
		"Selections:="		, "coil_2_Section1",
		"NewPartsModelFlag:="	, "Model"
	], 
	[
		"CreateGroupsForNewObjects:=", False
	])
oEditor.Delete(
	[
		"NAME:Selections",
		"Selections:="		, "coil_2_Section1_Separate1,coil_2_Section1_Separate2,coil_2_Section1_Separate3,coil_2_Section1_Separate4,coil_2_Section1_Separate5,coil_2_Section1_Separate6,coil_2_Section1_Separate7,coil_2_Section1_Separate8,coil_2_Section1_Separate9,coil_2_Section1_Separate10,coil_2_Section1_Separate11,coil_2_Section1_Separate12,coil_2_Section1_Separate13,coil_2_Section1_Separate14,coil_2_Section1_Separate15,coil_2_Section1_Separate16,coil_2_Section1_Separate17,coil_2_Section1_Separate18,coil_2_Section1_Separate19,coil_2_Section1_Separate20,coil_2_Section1_Separate21,coil_2_Section1_Separate22,coil_2_Section1_Separate23"
	])
oModule.AssignCurrent(
	[
		"NAME:Current2",
		"Objects:="		, ["coil_2_Section1"],
		"Current:="		, "1A",
		"IsSolid:="		, False,
		"Point out of terminal:=", False
	])
oEditor.CreateRegion(
	[
		"NAME:RegionParameters",
		"+XPaddingType:="	, "Percentage Offset",
		"+XPadding:="		, "200",
		"-XPaddingType:="	, "Percentage Offset",
		"-XPadding:="		, "200",
		"+YPaddingType:="	, "Percentage Offset",
		"+YPadding:="		, "200",
		"-YPaddingType:="	, "Percentage Offset",
		"-YPadding:="		, "200",
		"+ZPaddingType:="	, "Percentage Offset",
		"+ZPadding:="		, "200",
		"-ZPaddingType:="	, "Percentage Offset",
		"-ZPadding:="		, "200",
		[
			"NAME:BoxForVirtualObjects",
			[
				"NAME:LowPoint", 
				1, 
				1, 
				1
			],
			[
				"NAME:HighPoint", 
				-1, 
				-1, 
				-1
			]
		]
	], 
	[
		"NAME:Attributes",
		"Name:="		, "Region",
		"Flags:="		, "Wireframe#",
		"Color:="		, "(143 175 143)",
		"Transparency:="	, 0,
		"PartCoordinateSystem:=", "Global",
		"UDMId:="		, "",
		"MaterialValue:="	, "\"vacuum\"",
		"SurfaceMaterialValue:=", "\"\"",
		"SolveInside:="		, True,
		"ShellElement:="	, False,
		"ShellElementThickness:=", "nan ",
		"ReferenceTemperature:=", "nan ",
		"IsMaterialEditable:="	, True,
		"UseMaterialAppearance:=", False,
		"IsLightweight:="	, False
	])
oModule = oDesign.GetModule("AnalysisSetup")
oModule.InsertSetup("Magnetostatic", 
	[
		"NAME:Setup1",
		"Enabled:="		, True,
		[
			"NAME:MeshLink",
			"ImportMesh:="		, False
		],
		"MaximumPasses:="	, 10,
		"MinimumPasses:="	, 2,
		"MinimumConvergedPasses:=", 1,
		"PercentRefinement:="	, 30,
		"SolveFieldOnly:="	, False,
		"PercentError:="	, 1,
		"SolveMatrixAtLast:="	, True,
		"UseNonLinearIterNum:="	, False,
		"UseIterativeSolver:="	, False,
		"RelativeResidual:="	, 1E-06,
		"NonLinearResidual:="	, 0.001,
		"SmoothBHCurve:="	, False,
		[
			"NAME:MuOption",
			"MuNonLinearBH:="	, True
		]
	])

