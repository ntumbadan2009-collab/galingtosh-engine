"""Bounded deterministic 3D wireframes with perspective projection.

Only geometric cube/sphere rotation templates, no executable user code,
asset loading, invented scientific scale, or AI-generated image.
"""
from __future__ import annotations
import math
from PIL import ImageDraw

def draw_geometry(draw:ImageDraw.ImageDraw, kind:str, box:tuple[int,int,int,int], time_sec:float,duration:float,accent:tuple[int,int,int]):
    x0,y0,x1,y1=box
    radius=min(x1-x0,y1-y0)*.28
    cx,cy=(x0+x1)/2,(y0+y1)/2
    angle=math.tau*time_sec/max(.25,duration)
    c,s=math.cos(angle),math.sin(angle)
    tilt=.33
    def project(p):
        x,y,z=p
        x,z=c*x+s*z,-s*x+c*z
        y,z=math.cos(tilt)*y-math.sin(tilt)*z, math.sin(tilt)*y+math.cos(tilt)*z
        factor=4/(4-z)
        return cx+radius*x*factor,cy-radius*y*factor,z
    width=max(1,round(radius/55))
    if kind=="cube_rotation":
        vertices=[(x,y,z) for x in (-1,1) for y in (-1,1) for z in (-1,1)]
        p=[project(v) for v in vertices]
        edges=[(i,j) for i in range(8) for j in range(i+1,8) if sum(a!=b for a,b in zip(vertices[i],vertices[j]))==1]
        for i,j in sorted(edges,key=lambda ij:(p[ij[0]][2]+p[ij[1]][2])/2):
            near=(p[i][2]+p[j][2])>=0
            shade=accent if near else tuple(int(a*.45) for a in accent)
            draw.line((p[i][:2],p[j][:2]),fill=shade,width=width+int(near))
        for x,y,z in p:
            if z>=0:draw.ellipse((x-width,y-width,x+width,y+width),fill=(240,245,250))
    elif kind=="sphere_rotation":
        def spherical(lat,lon):
            return math.cos(lat)*math.cos(lon),math.sin(lat),math.cos(lat)*math.sin(lon)
        curves=[[spherical(lat,k*math.tau/64) for k in range(65)] for lat in [-math.pi/3,-math.pi/6,0,math.pi/6,math.pi/3]]
        curves.extend([[spherical(-math.pi/2+k*math.pi/48,lon) for k in range(49)] for lon in [k*math.tau/10 for k in range(10)]])
        for curve in curves:
            points=[project(p) for p in curve]
            for a,b in zip(points,points[1:]):
                if a[2]+b[2]>=0:
                    draw.line((a[:2],b[:2]),fill=accent,width=width)
        # Reference meridian, rotating with the sphere; not a geographic map.
        points=[project(spherical(-math.pi/2+k*math.pi/48,0)) for k in range(49)]
        for a,b in zip(points,points[1:]):
            if a[2]+b[2]>=0:draw.line((a[:2],b[:2]),fill=(250,222,139),width=width+1)
    else:raise ValueError("Forme 3D inconnue.")
