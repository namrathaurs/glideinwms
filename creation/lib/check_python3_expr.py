#!/usr/bin/env python3
#
# Project:
#   glideinWMS
#
# Description:
#   Validate expressions in frontend.xml for compatibility with Python 3
#
# Author:
#   Bruno Coimbra
#

import sys
import ast
import xml.etree.ElementTree as ET
import difflib
import argparse

from types import SimpleNamespace

# Initialize a refactoring tool if 2to3 is available
try:
    from lib2to3 import refactor
    fixer_pkg = "lib2to3.fixes"
    avail_fixes = set(refactor.get_fixers_from_package(fixer_pkg))
    rt = refactor.RefactoringTool(avail_fixes)
except:
    rt = None

CONFIG_FILE = "/etc/gwms-frontend/frontend.xml"

def check_syntax(code):
    """Validates the Python 3 syntax of a code.

    Args:
        code (str): Code to validate.

    Returns:
        str: None if code is valid. Error message if the code is invalid.
    """

    error = None
    try:
        ast.parse(code)
    except SyntaxError as e:
        error = f"{e.msg} at \"{e.text.strip()}\" ({e.lineno},{e.offset})"

    return error

def check_2to3(code, patch=False, refactoring_tool=rt):
    """Evaluates an expression using 2to3 and returns refactoring suggestions.

    Args:
        expr (str): Expression to evaluate.
        diff (bool): If True, returns a patch with the suggested changes.
        refactoring_tool (RefactoringTool): Used to by 2to3 to evaluate the expression.

    Returns:
        str: 2to3 suggested code. None if the expression conforms with Python 3.
    """

    suggestion = None
    if refactoring_tool:
        try:
            suggested_code = str(refactoring_tool.refactor_string(f"{code}\n", None))[:-1]
            diff = '\n'.join(difflib.unified_diff(code.split("\n"), suggested_code.split("\n"), lineterm=''))
            if len(diff) > 0:
                if patch:
                    suggestion = diff
                else:
                    suggestion = suggested_code
        except:
            suggested_code = "could not parse the expression"
    
    return suggestion

def findall_path(root, tag, elements=[]):
    """Finds all elements in `root` of `tag` type preserving their paths.

    Args:
        root (Element): Root element to be searched.
        tag (str): Tag to search.
        elements (list, optional): List of found elements. To be used with recursive calls. Defaults to [].

    Returns:
        list: List of found elements.
    """
    if not isinstance(root, SimpleNamespace):
        element = SimpleNamespace()
        element.data = root
        element.parent = None
    else:
        element = root

    for child in element.data.getchildren():
        newElement = SimpleNamespace()
        newElement.data = child
        newElement.parent = element
        if child.tag == tag:
            elements.append(newElement)
        findall_path(newElement, tag, elements)
    
    return elements

def element_name(element):
    """Finds the name attribute of element. Returns `None` if nothing is found.

    Args:
        element (Element): Element to search.

    Returns:
        str: Element name.
    """

    name_attrib = "name"
    if element.tag == "frontend":
        name_attrib = "frontend_name"

    try:
        return element.attrib[name_attrib]
    except KeyError:
        return None

def _log(text, silent=False):
    if silent:
        return
    sys.stdout.write(text)

def main(config_file, enforce_2to3=False, silent=False, refactoring_tool=rt):
    """Parse the Frontend configuration in config_file and validate Python code.

    Args:
        config_file (str): Path to the frontend configuration file.
        enforce_2to3 (bool, optional): Treats 2to3 suggestions as errors. Defaults to False.

    Returns:
        bool: True if the file is valid and False otherwise.
        list: List of results for every element evaluated
    """

    if enforce_2to3 and not refactoring_tool:
        _log("2to3 not found and will not be enforced")

    passed = True
    report = []

    try:
        tree = ET.parse(config_file)
    except IOError:
        return "Config file not readable: %s" % config_file
    except:
        return "Error parsing config file: %s" % config_file
    
    # Recursively finds all <match> elements in the XML
    for element in findall_path(tree.getroot(), "match"):
        # Validates match expressions attributes
        if "match_expr" in element.data.attrib:
            expr = element.data.attrib["match_expr"]
            location = f"{element.parent.data.tag} {element_name(element.parent.data)}"
            _log(f"\n\nEvaluating expression \"{expr}\"\n", silent)
            _log(f"at {location}\n", silent)
            result = {}
            result["type"] = "match_expr"
            result["value"] = expr
            result["location"] = location
            error = check_syntax(expr)
            _log("\nSyntax check: ", silent)
            if not error:
                _log("passed\n", silent)
                result["valid"] = True
                result["error"] = None
            else:
                _log(f"{error}\n", silent)
                result["valid"] = False
                result["error"] = error
                passed = False
            if refactoring_tool:
                _log("2to3 suggestion:", silent)
                suggestion = check_2to3(expr)
                if suggestion and suggestion != expr:
                    _log(f"\n{suggestion}\n", silent)
                    result["2to3"] = suggestion
                    if enforce_2to3:
                        passed = False
                else:
                    _log(f" none\n", silent)
                    result["2to3"] = None
            report.append(result)
        #validates policy files
        if "policy_file" in element.data.attrib:
            path = element.data.attrib["policy_file"]
            location = f"{element.parent.data.tag} {element_name(element.parent.data)}"
            _log(f"\n\nEvaluating policy file \"{path}\"\n", silent)
            _log(f"at {location}\n", silent)
            try:
                text = open(path).read()
            except FileNotFoundError as e:
                error = f"{e.strerror}: {e.filename}"
                _log(f"\n{error}\n", silent)
                result["valid"] = False
                result["error"] = error
                passed = False
                continue
            result = {}
            result["type"] = "policy_file"
            result["value"] = path
            result["location"] = location
            result["code"] = text
            error = check_syntax(text)
            _log("\nSyntax check: ", silent)
            if not error:
                _log("passed\n", silent)
                result["valid"] = True
                result["error"] = None
            else:
                _log(f"{error}\n", silent)
                result["valid"] = False
                result["error"] = error
                passed = False
            if refactoring_tool:
                _log("2to3 suggestion:", silent)
                suggestion = check_2to3(text, patch=True)
                if suggestion and suggestion != text:
                    _log(f"\n{suggestion}\n", silent)
                    result["2to3"] = suggestion
                    if enforce_2to3:
                        passed = False
                else:
                    _log(f" none\n", silent)
                    result["2to3"] = None
            report.append(result)

    return passed, report

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Validate expressions in frontend.xml for compatibility with Python 3.')
    parser.add_argument("-f", "--file", metavar="PATH", type=str, help="path to the configuration file")
    parser.add_argument("-s", "--silent", action="store_true", help="silent mode")
    parser.add_argument("--enforce-2to3", action="store_true", help="treats 2to3 suggestions as errors")
    args = parser.parse_args()

    if args.file:
        config_file = args.file
    else:
        config_file = CONFIG_FILE
    
    passed, _ = main(config_file, args.enforce_2to3, args.silent)
    if passed:
        _log("\n\nPassed (configuration compatible with python3)\n", args.silent)
        exit(0)
    else:
        _log("\n\nFailed (invalid python3 in configuration)\n", args.silent)
        exit(1)