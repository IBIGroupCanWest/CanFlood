# -*- coding: utf-8 -*-
"""
/***************************************************************************
 CanFlood_inPrep
                                 A QGIS plugin
 This plugin preps CanFlood data
 Generated by Plugin Builder: http://g-sherman.github.io/Qgis-Plugin-Builder/
                             -------------------
        begin                : 2020-02-19
        copyright            : (C) 2020 by Tony De Crescenzo
        email                : tony.decrescenzo@ibigroup.com
        git sha              : $Format:%H$
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
 This script initializes the plugin, making it known to QGIS.
"""


# noinspection PyPep8Naming
def classFactory(iface):  # pylint: disable=invalid-name
    """Load CanFlood_inPrep class from file CanFlood_inPrep.

    :param iface: A QGIS interface instance.
    :type iface: QgsInterface
    """
    #
    from .canFlood_inPrep import CanFlood_inPrep
    return CanFlood_inPrep(iface)
